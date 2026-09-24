"""
process_car_dissolve.py — área das camadas ambientais do CAR sem dupla contagem.

process_car_layers.py soma a área declarada de cada polígono. Como o CAR é
declaratório e admite cadastros sobrepostos, a soma estoura o território: no
Acre, 11 dos 22 municípios passam de 100% da área municipal e Xapuri chega a
421%. Aqui cada camada é dissolvida por município antes de medir, então a área
onde dois cadastros se sobrepõem é contada uma vez só.

O município vem do código IBGE embutido em `cod_imovel` (UF-<7díg>-<hash>). Com
--recortar, a geometria dissolvida ainda é interceptada com a malha municipal,
o que corrige a parcela do imóvel que se estende para o município vizinho.

Cadastros cancelados (ind_status = CA) ficam de fora: são declarações que o
próprio SICAR invalidou, e em alguns estados passam de 20% da área registrada.
O método vai gravado na saída, e trocar de método invalida as medições
anteriores da UF — elas vão para _arquivo/ e são refeitas, para que o painel
nunca compare estados medidos de jeitos diferentes.

A memória fica limitada a um bloco de municípios por vez. Primeiro se leem só
os atributos, para saber de que município é cada feição, e o índice .shx dá o
tamanho exato de cada uma; os municípios são agrupados em blocos até um teto em
MB, e cada bloco é lido por identificador, unido, medido e descartado. Sem isso
a APP de SP, com 21,7 GB, não caberia: a união de todos os municípios ficaria em
memória até o fim.

Várias filas podem rodar juntas, sobre camadas diferentes ou sobre a mesma
lista de pendências: cada camada é reservada por quem a pega (em _reservas/,
com o PID do dono, liberada se ele morrer), e a gravação de cada UF é feita sob
trava de arquivo, para que uma fila não apague a camada que a outra acabou de
gravar. O limite é a memória, não a CPU: numa máquina de 32 GB com o uso normal
de outros programas, quatro filas da APP rodaram a 90% de um núcleo cada; com
cinco ou seis, a disputa por memória derrubou todas para uns 15%. Um município
nunca é partido, então o maior vira um bloco sozinho — São Félix do Xingu (PA),
com 157 mil feições e 1,36 GB de APP, levou 3,4 horas de cálculo.

A Bahia tem medidas compostas, porque o CEFIR registra o imóvel de outro jeito
(ver docs/CAR_LIMITATIONS.md): vegetação nativa, reserva legal e APP são fatias
disjuntas, e não existe área consolidada para imóvel privado. --compostas gera
car_ambiental_composta_BA com a vegetação nativa comparável ao padrão nacional
e a área de atividade produtiva declarada. Sergipe tem a vegetação nativa
composta pelo mesmo motivo: lá a maioria dos imóveis declara reserva legal sem
declarar a vegetação nativa.

Uso:
  python process_car_dissolve.py --uf MT
  python process_car_dissolve.py --uf MT --camadas uso_restrito   # teste rápido
  python process_car_dissolve.py --pendentes [--camadas ...]
  python process_car_dissolve.py --compostas --uf BA
  python process_car_dissolve.py --uf MT --incluir-cancelados     # método antigo
  python process_car_dissolve.py --pendentes --camadas app --teto-mb 700
  python process_car_dissolve.py --pendentes --camadas app --maiores-primeiro   # em N terminais
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import (  # noqa: E402
    RAW_DIR, PROCESSED_DIR, CRS_AREA, CRS_STORAGE, cod_mun7, save_table,
)

GEO = PROCESSED_DIR / "geospatial"
ARQUIVO = GEO / "_arquivo"
REGISTRO = GEO / "car_dissolve_fila.log"
CAMADAS = ["area_consolidada", "vegetacao_nativa", "reserva_legal", "app", "uso_restrito"]
TETO_MB = 1000

COMPOSTAS = {
    "BA": {
        # No CEFIR as três camadas não se sobrepõem; no padrão nacional a
        # vegetação nativa já contém reserva legal e APP com vegetação. Área
        # degradada em RL e APP não é vegetação nativa e sai da conta.
        "vegetacao_nativa_composta": {
            "somar": [("sicar", "vegetacao_nativa"), ("sicar", "reserva_legal"), ("sicar", "app")],
            "subtrair": [("cefir", "area_degradada_reserva_legal"), ("cefir", "area_degradada_app")],
        },
        # O CEFIR não tem área consolidada para imóvel privado; tem a área das
        # atividades desenvolvidas. Os assentamentos e comunidades tradicionais
        # que o SICAR repassa como área consolidada entram junto.
        "area_atividade": {
            "somar": [("cefir", "atividade_desenvolvida"), ("sicar", "area_consolidada")],
        },
    },
    # Em Sergipe, 82% dos imóveis que declaram reserva legal não declaram
    # vegetação nativa, e só um terço da reserva legal cai dentro dela: parte da
    # vegetação nativa só aparece na reserva legal e na APP. Sem camada de área
    # degradada no SICAR, nada é descontado.
    "SE": {
        "vegetacao_nativa_composta": {
            "somar": [("sicar", "vegetacao_nativa"), ("sicar", "reserva_legal"), ("sicar", "app")],
        },
    },
}


def metodo(recortar: bool, incluir_cancelados: bool) -> str:
    base = "dissolve+recorte" if recortar else "dissolve"
    return base if incluir_cancelados else f"{base}, sem cancelados"


def anotar(msg: str):
    """Registro linha a linha: sobrevive a saída em pipe e a processo interrompido."""
    linha = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(linha, flush=True)
    with open(REGISTRO, "a", encoding="utf-8") as f:
        f.write(linha + "\n")


# ─── fontes ──────────────────────────────────────────────────────────────────

@dataclass
class Fonte:
    rotulo: str
    arquivos: list[Path]
    atributos: Callable  # (arquivo, estatisticas) -> DataFrame indexado por fid, coluna cod_municipio


def _mun_do_car(v) -> str | None:
    m = re.search(r"-(\d{7})-", str(v))
    return cod_mun7(m.group(1)) if m else None


def _id(x) -> str | None:
    try:
        return str(int(float(x)))
    except (TypeError, ValueError):
        return None


def _metrico(g):
    if g.crs is None:
        g = g.set_crs(CRS_STORAGE)
    return g.to_crs(CRS_AREA)


def _fonte_sicar(uf: str, camada: str, incluir_cancelados: bool) -> Fonte:
    import pyogrio

    def atributos(arq, est):
        filtrar = not incluir_cancelados and "ind_status" in pyogrio.read_info(arq)["fields"]
        a = pyogrio.read_dataframe(arq, columns=["cod_imovel"] + (["ind_status"] if filtrar else []),
                                   read_geometry=False, fid_as_index=True)
        if filtrar:
            cancelado = a["ind_status"].astype(str).str.upper().eq("CA")
            est["canceladas"] += int(cancelado.sum())
            a = a[~cancelado]
        return a["cod_imovel"].map(_mun_do_car).rename("cod_municipio").to_frame()

    d = RAW_DIR / "car" / uf / camada
    return Fonte(f"SICAR/{uf}/{camada}", sorted(d.rglob("*.shp")) if d.exists() else [], atributos)


_MAPA_CEFIR: dict[str, str] | None = None


def _mapa_cefir() -> dict[str, str]:
    """ide_imovel → município, a partir do número do CAR (BA-<7díg>-...)."""
    global _MAPA_CEFIR
    if _MAPA_CEFIR is None:
        p = RAW_DIR / "cefir" / "BA" / "limite_atributos.csv"
        if not p.exists():
            raise SystemExit(f"{p} ausente — rode download/download_cefir_ba.py")
        d = pd.read_csv(p, dtype=str)
        cod = d["numero_car"].str.extract(r"^BA-(\d{7})-", expand=False)
        ok = cod.notna() & d["ide_imovel"].notna()
        _MAPA_CEFIR = dict(zip(d.loc[ok, "ide_imovel"].map(_id), cod[ok].map(cod_mun7)))
    return _MAPA_CEFIR


def _fonte_cefir(camada: str) -> Fonte:
    import pyogrio

    def atributos(arq, est):
        mapa = _mapa_cefir()
        a = pyogrio.read_dataframe(arq, columns=["ide_imovel"], read_geometry=False, fid_as_index=True)
        return a["ide_imovel"].map(lambda x: mapa.get(_id(x))).rename("cod_municipio").to_frame()

    d = RAW_DIR / "cefir" / "BA" / camada
    return Fonte(f"CEFIR/BA/{camada}", sorted(d.rglob("*.shp")) if d.exists() else [], atributos)


def _fonte(origem: str, uf: str, camada: str, incluir_cancelados: bool) -> Fonte:
    if origem == "sicar":
        return _fonte_sicar(uf, camada, incluir_cancelados)
    if origem == "cefir":
        return _fonte_cefir(camada)
    raise ValueError(origem)


# ─── geometria ───────────────────────────────────────────────────────────────

def _so_area(g):
    """Parte de área de uma geometria; None se não sobrar área nenhuma."""
    from shapely import get_parts, union_all
    if g is None or g.is_empty:
        return None
    if g.geom_type in ("Polygon", "MultiPolygon"):
        return g
    partes = [p for p in get_parts(g) if p.geom_type in ("Polygon", "MultiPolygon")]
    if not partes:
        return None
    return partes[0] if len(partes) == 1 else _robusto(union_all, partes)


def _sanear(g):
    """Polígono válido a partir de uma geometria inválida do CAR.

    O make_valid padrão reconstrói pelo traçado e, em polígonos muito
    degenerados, devolve área misturada com linha — e pode abortar ali mesmo
    ("Overlay input is mixed-dimension", visto no AM). O método estrutural
    preserva a leitura de área; buffer(0) é o último recurso. O que sobrar
    de linha ou ponto é descartado: tem área zero e só quebraria a união.
    """
    from shapely import make_valid
    from shapely.errors import GEOSException
    try:
        g = make_valid(g, method="structure", keep_collapsed=False)
    except GEOSException:
        try:
            g = g.buffer(0)
        except GEOSException:
            return None
    return _so_area(g)


GRADES_M = (0.001, 0.01, 0.1)


def _na_grade(x, grade: float):
    """Geometria (ou lista) arredondada à grade e válida nela."""
    import numpy as np
    from shapely import set_precision
    if isinstance(x, (list, tuple)):
        x = np.asarray(x, dtype=object)
    return set_precision(x, grade)


def _robusto(operacao, *args, est: dict | None = None):
    """Operação do GEOS que, se falhar em precisão exata, refaz em grade fixa.

    Unir centenas de milhares de polígonos quase coincidentes — a APP traz o
    "APP Total" colado às partes que o compõem — esbarra na aritmética de ponto
    flutuante ("non-noded intersection", "Ring edge missing"), mesmo com toda a
    geometria válida. Pedir a grade só na operação não basta: arredondar colapsa
    polígonos finos, que ficam inválidos na nova precisão, e o OverlayNG só é
    robusto com entradas válidas nela. Por isso cada geometria é arredondada de
    forma válida antes (set_precision). Em Água Azul do Norte (PA), a exata e a
    grade pura falham até 1 m; arredondada válida a 1 mm, mede. A grade só entra
    quando a exata falha, então o que já media continua medindo igual.
    """
    from shapely.errors import GEOSException
    try:
        return operacao(*args)
    except GEOSException as e:
        erro = e
    for grade in GRADES_M:
        try:
            resultado = operacao(*(_na_grade(a, grade) for a in args), grid_size=grade)
        except GEOSException as e:
            erro = e
            continue
        if est is not None:
            est["arredondadas"] += 1
            est["grade_max"] = max(est.get("grade_max", 0), grade)
        return resultado
    raise erro


def _area_clipper(somar: list, tirar: list | None = None, escala: int = 1000) -> float:
    """Área (ha) da união de somar, menos a de tirar, em aritmética inteira (mm).

    Último recurso para quando o GEOS falha em todas as grades: o Clipper não
    usa ponto flutuante na interseção de arestas, então não tem como esbarrar
    nesse limite. Devolve só a área, que é o que a medição precisa.
    """
    import numpy as np
    import pyclipper
    import shapely

    pc = pyclipper.Pyclipper()

    def adicionar(geoms, papel):
        for g in geoms:
            for p in shapely.get_parts(shapely.orient_polygons(g)):
                for anel in (p.exterior, *p.interiors):
                    c = np.round(np.asarray(anel.coords)[:-1] * escala).astype(np.int64)
                    if len(c) >= 3:
                        try:
                            pc.AddPath(c.tolist(), papel, True)
                        except pyclipper.ClipperException:
                            pass  # anel degenerado depois do arredondamento: área zero

    adicionar(somar, pyclipper.PT_SUBJECT)
    if tirar:
        adicionar(tirar, pyclipper.PT_CLIP)
    tipo = pyclipper.CT_DIFFERENCE if tirar else pyclipper.CT_UNION
    sol = pc.Execute(tipo, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)
    return sum(pyclipper.Area(s) for s in sol) / escala ** 2 / 10_000.0


def _preparar(geoms, est) -> list:
    """Só polígonos válidos. A checagem é vetorizada; o conserto, um a um."""
    import numpy as np
    import shapely
    geoms = np.asarray(geoms, dtype=object)
    geoms = geoms[~(shapely.is_missing(geoms) | shapely.is_empty(geoms))]
    validas = shapely.is_valid(geoms)
    poligonais = np.isin(shapely.get_type_id(geoms), (3, 6))
    prontas = list(geoms[validas & poligonais])
    est["invalidas"] += int((~validas).sum())
    for g in geoms[~(validas & poligonais)]:
        g = _so_area(g) if shapely.is_valid(g) else _sanear(g)
        if g is None:
            est["descartadas"] += 1
        else:
            prontas.append(g)
    return prontas


def _tamanhos(arq: Path):
    """Bytes de geometria de cada feição, lidos do índice .shx do shapefile."""
    import numpy as np
    shx = arq.with_suffix(".shx")
    if shx.exists():
        return np.fromfile(shx, dtype=">i4", offset=100)[1::2].astype("int64") * 2
    import pyogrio
    n = pyogrio.read_info(arq)["features"]
    return np.full(n, arq.stat().st_size // max(n, 1), dtype="int64")


def _indice(fontes: list[Fonte], est: dict) -> tuple[pd.DataFrame, list[Path]]:
    """Uma linha por feição — arquivo, fid, município e bytes — sem ler geometria."""
    arquivos, partes = [], []
    for fonte in fontes:
        for arq in fonte.arquivos:
            a = fonte.atributos(arq, est)
            a["bytes"] = _tamanhos(arq)[a.index.to_numpy()]
            a["arq"] = len(arquivos)
            arquivos.append(arq)
            partes.append(a.rename_axis("fid").reset_index())
    if not partes:
        return pd.DataFrame(columns=["fid", "cod_municipio", "bytes", "arq"]), arquivos
    idx = pd.concat(partes, ignore_index=True)
    sem = idx["cod_municipio"].isna()
    est["sem_municipio"] += int(sem.sum())
    return idx[~sem], arquivos


def _blocos(idx: pd.DataFrame, teto_bytes: int) -> list[list[str]]:
    """Municípios agrupados em ordem, cada bloco até o teto de bytes de geometria."""
    pesos = idx.groupby("cod_municipio")["bytes"].sum().sort_index()
    blocos, atual, soma = [], [], 0
    for cod, b in pesos.items():
        if atual and soma + b > teto_bytes:
            blocos.append(atual)
            atual, soma = [], 0
        atual.append(cod)
        soma += b
    if atual:
        blocos.append(atual)
    return blocos


def _ler_bloco(linhas: pd.DataFrame, arquivos: list[Path], est: dict) -> dict[str, list]:
    """Geometrias das linhas pedidas, lidas por fid e agrupadas por município."""
    import numpy as np
    import pyogrio
    por_mun: dict[str, list] = {}
    for i_arq, sub in linhas.groupby("arq"):
        sub = sub.set_index("fid")
        g = pyogrio.read_dataframe(arquivos[i_arq], fids=np.sort(sub.index.to_numpy()),
                                   columns=[], fid_as_index=True)
        g["cod_municipio"] = sub["cod_municipio"].reindex(g.index).to_numpy()
        g = _metrico(g)
        est["lidas"] += len(g)
        for cod, ix in g.groupby("cod_municipio").indices.items():
            por_mun.setdefault(cod, []).extend(_preparar(g.geometry.values[ix], est))
    return por_mun


def _novo_est() -> dict:
    return {"lidas": 0, "invalidas": 0, "descartadas": 0, "canceladas": 0,
            "sem_municipio": 0, "arredondadas": 0, "clipper": 0, "inicio": time.time()}


def _medir_fontes(fontes: list[Fonte], subtrair: list[Fonte] | None = None,
                  recortar: bool = False) -> tuple[dict[str, float], dict]:
    """Área (ha) por município da união das fontes, menos a união de subtrair."""
    from shapely import difference, intersection, union_all
    from shapely.errors import GEOSException
    est = _novo_est()
    idx, arquivos = _indice(fontes, est)
    if subtrair:
        idx_sub, arq_sub = _indice(subtrair, _novo_est())
    blocos = _blocos(idx, TETO_MB * 1_000_000)
    print(f"    {len(idx):,} feições em {idx['cod_municipio'].nunique()} municípios, "
          f"{idx['bytes'].sum() / 1e9:.1f} GB de geometria, {len(blocos)} bloco(s)", flush=True)
    areas: dict[str, float] = {}
    for i, bloco in enumerate(blocos, 1):
        linhas = idx[idx["cod_municipio"].isin(bloco)]
        geoms = _ler_bloco(linhas, arquivos, est)
        tirar = (_ler_bloco(idx_sub[idx_sub["cod_municipio"].isin(bloco)], arq_sub, _novo_est())
                 if subtrair else {})
        malha = _malha_municipal(geoms.keys()) if recortar else None
        for cod, lista in geoms.items():
            if not lista:
                continue
            try:
                u = _robusto(union_all, lista, est=est)
                if tirar.get(cod):
                    u = _robusto(difference, u, _robusto(union_all, tirar[cod], est=est), est=est)
                if malha is not None and cod in malha.index:
                    u = _robusto(intersection, u, malha.loc[cod], est=est)
                areas[cod] = u.area / 10_000.0
            except GEOSException as e:
                if recortar:
                    raise RuntimeError(f"município {cod}: {e}") from e
                areas[cod] = _area_clipper(lista, tirar.get(cod))
                est["clipper"] += 1
                print(f"      {cod}: GEOS falhou em todas as grades, medido pelo Clipper", flush=True)
        del geoms, tirar
        print(f"    bloco {i}/{len(blocos)}: {len(bloco)} municípios, {len(linhas):,} feições, "
              f"{linhas['bytes'].sum() / 1e6:,.0f} MB ({time.time() - est['inicio']:.0f}s)", flush=True)
    return areas, est


def _malha_municipal(codigos):
    """Geometrias dos municípios pedidos, em CRS métrico, para o recorte."""
    import geopandas as gpd
    p = GEO / "malha_municipios.parquet"
    if not p.exists():
        raise SystemExit(
            "malha_municipios.parquet ausente em data/processed/geospatial/. "
            "Rode sem --recortar ou gere a malha primeiro.")
    m = gpd.read_parquet(p)
    m = m[m["cod_municipio"].astype(str).isin(set(codigos))]
    return m.to_crs(CRS_AREA).set_index("cod_municipio")["geometry"]


def _resumo(rotulo: str, areas: dict, est: dict):
    extras = [f"{est[k]:,} {nome}" for k, nome in
              (("canceladas", "canceladas fora"), ("invalidas", "saneadas"),
               ("descartadas", "sem área"), ("sem_municipio", "sem município"),
               ("arredondadas", "operações em grade fixa"),
               ("clipper", "municípios pelo Clipper"))
              if est[k]]
    if est.get("grade_max"):
        extras.append(f"grade máxima {est['grade_max']} m")
    print(f"  {rotulo}: {len(areas)} municípios, {sum(areas.values()):,.0f} ha de "
          f"{est['lidas']:,} feições em {time.time() - est['inicio']:.0f}s"
          + (f" ({'; '.join(extras)})" if extras else ""), flush=True)


# ─── medições ────────────────────────────────────────────────────────────────

def dissolver_camada(uf: str, camada: str, recortar: bool,
                     incluir_cancelados: bool = False) -> pd.Series | None:
    """Área dissolvida (ha) por município, para uma camada do SICAR."""
    fonte = _fonte_sicar(uf, camada, incluir_cancelados)
    if not fonte.arquivos:
        return None
    areas, est = _medir_fontes([fonte], recortar=recortar)
    if not areas:
        return None
    _resumo(camada, areas, est)
    return pd.Series(areas, name=f"{camada}_ha").rename_axis("cod_municipio")


def medir_composta(uf: str, nome: str, recortar: bool,
                   incluir_cancelados: bool = False) -> pd.Series:
    spec = COMPOSTAS[uf][nome]
    somar = [_fonte(o, uf, c, incluir_cancelados) for o, c in spec["somar"]]
    tirar = [_fonte(o, uf, c, incluir_cancelados) for o, c in spec.get("subtrair", [])]
    faltam = [f.rotulo for f in somar + tirar if not f.arquivos]
    if faltam:
        raise SystemExit(f"{nome}: sem arquivos para {', '.join(faltam)}")
    areas, est = _medir_fontes(somar, subtrair=tirar or None, recortar=recortar)
    _resumo(nome, areas, est)
    return pd.Series(areas, name=f"{nome}_ha").rename_axis("cod_municipio")


# ─── gravação e fila ─────────────────────────────────────────────────────────

@contextmanager
def _trava(alvo: Path, abandono_s: int = 900):
    """Exclusão mútua na gravação de uma UF entre filas que rodam juntas."""
    trava = alvo.parent / f"{alvo.name}.lock"
    while True:
        try:
            fd = os.open(trava, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                # Gravar leva segundos; uma trava tão velha é de processo morto no meio.
                if time.time() - trava.stat().st_mtime > abandono_s:
                    trava.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            time.sleep(0.5)
    try:
        yield
    finally:
        trava.unlink(missing_ok=True)


def _metodo_do_arquivo(p: Path) -> str | None:
    d = pd.read_parquet(p, columns=["metodo"])
    return d["metodo"].iloc[0] if len(d) else None


def _arquivar(alvo: Path, motivo: str):
    ARQUIVO.mkdir(exist_ok=True)
    carimbo = time.strftime("%Y%m%d-%H%M%S")
    for ext in (".parquet", ".csv"):
        p = alvo.with_suffix(ext)
        if p.exists():
            p.rename(ARQUIVO / f"{alvo.name}_{carimbo}{ext}")
    anotar(f"{alvo.name} arquivado ({motivo})")


def _gravar(out: pd.DataFrame, uf: str, met: str, prefixo: str = "car_ambiental_dissolve"):
    alvo = GEO / f"{prefixo}_{uf}"
    with _trava(alvo):
        anterior = alvo.with_suffix(".parquet")
        if anterior.exists():
            antigo = _metodo_do_arquivo(anterior)
            if antigo != met:
                _arquivar(alvo, f"medido por '{antigo}', agora '{met}'")
            else:
                velho = pd.read_parquet(anterior)
                novas = [c for c in out.columns if c.endswith("_ha")]
                velho = velho.drop(columns=[c for c in novas if c in velho.columns])
                out = velho.drop(columns=["uf", "metodo"], errors="ignore").merge(
                    out.drop(columns=["uf", "metodo"], errors="ignore"), on="cod_municipio", how="outer")
        out["uf"] = uf
        out["metodo"] = met
        colunas = ["cod_municipio"] + sorted(c for c in out.columns if c.endswith("_ha"))
        out = out[colunas + ["uf", "metodo"]]
        save_table(out, alvo)
    print(f"  [{uf}] {len(out)} municípios · {', '.join(c[:-3] for c in colunas[1:])}", flush=True)


def salvar_camada(uf: str, camada: str, recortar: bool, incluir_cancelados: bool = False):
    """Mede uma camada e mescla no parquet da UF."""
    s = dissolver_camada(uf, camada, recortar, incluir_cancelados)
    if s is None:
        print(f"  {camada}: ausente em data/raw/car/{uf}/")
        return
    _gravar(s.to_frame().reset_index(), uf, metodo(recortar, incluir_cancelados))


def _invalidar_metodo_antigo(met: str):
    """Arquiva de uma vez as UFs medidas por outro método, antes de a fila começar."""
    for p in sorted(GEO.glob("car_ambiental_dissolve_*.parquet")):
        with _trava(p.with_suffix("")):
            antigo = _metodo_do_arquivo(p) if p.exists() else met
            if antigo != met:
                _arquivar(p.with_suffix(""), f"medido por '{antigo}', agora '{met}'")


def pendencias(quais: list[str] | None = None, met: str | None = None) -> dict[str, list[str]]:
    """UFs com camada extraída e ainda não medida pelo método atual, do mais barato ao mais caro."""
    from common import UFS
    met = met or metodo(False, False)
    alvo = quais or CAMADAS
    out = {}
    for uf in UFS:
        base = RAW_DIR / "car" / uf
        if not base.exists():
            continue
        extraidas = [c for c in alvo if (base / c).exists() and any((base / c).rglob("*.shp"))]
        if not extraidas:
            continue
        medidas = set()
        parquet_uf = GEO / f"car_ambiental_dissolve_{uf}.parquet"
        if parquet_uf.exists() and _metodo_do_arquivo(parquet_uf) == met:
            medidas = {c[:-3] for c in pd.read_parquet(parquet_uf).columns if c.endswith("_ha")}
        falta = [c for c in extraidas if c not in medidas]
        if falta:
            # Peso do shapefile aproxima o custo; começar pelas leves devolve
            # resultado cedo e deixa as caras por último.
            falta.sort(key=lambda c: sum(f.stat().st_size for f in (base / c).rglob("*.shp")))
            out[uf] = falta
    return out


def _rodar_tarefa(rotulo: str, uf: str, nome: str, fazer: Callable) -> bool:
    """Roda uma tarefa registrando início, fim ou falha; a falha não derruba a fila."""
    import traceback
    t1 = time.time()
    anotar(f"[{rotulo}] {uf}/{nome} iniciada")
    try:
        fazer()
    except Exception as e:
        anotar(f"[{rotulo}] {uf}/{nome} FALHOU: {type(e).__name__}: {e}")
        with open(REGISTRO, "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
        return False
    anotar(f"[{rotulo}] {uf}/{nome} ok em {(time.time() - t1) / 60:.0f} min")
    return True


def _executar(tarefas: list[tuple[str, str, Callable]]):
    """Roda uma lista de (uf, nome, função) em ordem."""
    total, falhas, t0 = len(tarefas), 0, time.time()
    for i, (uf, nome, fazer) in enumerate(tarefas, 1):
        falhas += not _rodar_tarefa(f"{i}/{total}", uf, nome, fazer)
    anotar(f"fila concluída em {(time.time() - t0) / 3600:.1f} h, {falhas} falha(s)")


def _vivo(pid: int) -> bool:
    """O processo ainda existe? No Windows, os.kill(pid, 0) mataria o processo."""
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        k.OpenProcess.restype = ctypes.c_void_p
        k.GetExitCodeProcess.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong))
        k.CloseHandle.argtypes = (ctypes.c_void_p,)
        h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        codigo = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(codigo))
        k.CloseHandle(h)
        return bool(ok) and codigo.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def _reservar(uf: str, camada: str) -> Path | None:
    """Reserva a camada para esta fila; None se outra fila viva já a pegou."""
    p = GEO / "_reservas" / f"{uf}_{camada}"
    p.parent.mkdir(exist_ok=True)
    for _ in range(100):
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                dono = int(p.read_text() or 0)
            except (FileNotFoundError, ValueError):
                dono = 0
            if dono and _vivo(dono):
                return None
            if dono or time.time() - p.stat().st_mtime > 5:
                p.unlink(missing_ok=True)  # dono morreu no meio da camada
            else:
                time.sleep(0.1)  # recém-criada, o PID ainda está sendo gravado
            continue
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return p
    return None


def _peso(uf: str, camada: str) -> int:
    return sum(f.stat().st_size for f in (RAW_DIR / "car" / uf / camada).rglob("*.shp"))


def rodar_pendentes(recortar: bool, quais: list[str] | None = None,
                    incluir_cancelados: bool = False, maiores_primeiro: bool = False):
    """Mede o que está pendente, dividindo o trabalho com outras filas que rodem juntas.

    Cada camada é reservada por quem a pega e as pendências são relidas antes de
    cada uma, então várias filas podem ser disparadas sobre a mesma lista: nenhuma
    repete o que outra já mediu ou está medindo. Com várias filas, começar pelas
    maiores equilibra o fim; com uma só, começar pelas leves devolve resultado cedo.
    """
    met = metodo(recortar, incluir_cancelados)
    _invalidar_metodo_antigo(met)
    pend = pendencias(quais, met)
    if not pend:
        print("[CAR dissolve] nada pendente: tudo que está extraído já foi medido.")
        return
    total = sum(len(v) for v in pend.values())
    eu = f"fila {os.getpid()}"
    anotar(f"{eu} iniciada ({met}): {total} camada(s) pendente(s) em {len(pend)} UF(s): {', '.join(pend)}")
    tentadas: set[tuple[str, str]] = set()
    falhas, t0 = 0, time.time()
    while True:
        ordem = [(uf, c) for uf, cs in pendencias(quais, met).items() for c in cs
                 if (uf, c) not in tentadas]
        if maiores_primeiro:
            ordem.sort(key=lambda t: -_peso(*t))
        pega = None
        for uf, c in ordem:
            reserva = _reservar(uf, c)
            if reserva is None:
                continue
            # Outra fila pode ter terminado a camada entre a leitura e a reserva.
            if c in pendencias([c], met).get(uf, []):
                pega = (uf, c, reserva)
                break
            reserva.unlink(missing_ok=True)
        if pega is None:
            break
        uf, c, reserva = pega
        tentadas.add((uf, c))
        try:
            falhas += not _rodar_tarefa(eu, uf, c, lambda: salvar_camada(uf, c, recortar, incluir_cancelados))
        finally:
            reserva.unlink(missing_ok=True)
    anotar(f"{eu} concluída em {(time.time() - t0) / 3600:.1f} h, {len(tentadas)} camada(s), {falhas} falha(s)")


def rodar_compostas(uf: str, recortar: bool, incluir_cancelados: bool = False):
    if uf not in COMPOSTAS:
        raise SystemExit(f"sem medidas compostas definidas para {uf}")
    met = metodo(recortar, incluir_cancelados)

    def fazer(nome):
        s = medir_composta(uf, nome, recortar, incluir_cancelados)
        _gravar(s.to_frame().reset_index(), uf, met, prefixo="car_ambiental_composta")

    anotar(f"compostas {uf} ({met}): {', '.join(COMPOSTAS[uf])}")
    _executar([(uf, nome, (lambda nome=nome: fazer(nome))) for nome in COMPOSTAS[uf]])


def main():
    global TETO_MB
    ap = argparse.ArgumentParser()
    ap.add_argument("--uf")
    ap.add_argument("--camadas", nargs="*", default=CAMADAS)
    ap.add_argument("--recortar", action="store_true",
                    help="intercepta com a malha municipal além de dissolver")
    ap.add_argument("--pendentes", action="store_true",
                    help="mede tudo que está extraído e ainda não foi medido")
    ap.add_argument("--compostas", action="store_true",
                    help="medidas compostas da UF (Bahia e Sergipe)")
    ap.add_argument("--incluir-cancelados", action="store_true",
                    help="mantém cadastros cancelados (método anterior a 2026-09-23)")
    ap.add_argument("--teto-mb", type=int, default=TETO_MB,
                    help="MB de geometria por bloco de municípios; menor gasta menos "
                         "memória, e um município sozinho nunca é partido")
    ap.add_argument("--maiores-primeiro", action="store_true",
                    help="com várias filas juntas, pega as camadas mais pesadas antes")
    args = ap.parse_args()
    TETO_MB = args.teto_mb

    if args.pendentes:
        # --camadas restringe a fila; sem ele, mede as cinco.
        escolhidas = args.camadas if args.camadas != CAMADAS else None
        rodar_pendentes(args.recortar, escolhidas, args.incluir_cancelados, args.maiores_primeiro)
        return
    if not args.uf:
        raise SystemExit("informe --uf ou use --pendentes")
    uf = args.uf.upper()
    if args.compostas:
        rodar_compostas(uf, args.recortar, args.incluir_cancelados)
        return
    print(f"[CAR dissolve/{uf}] camadas: {', '.join(args.camadas)}")
    for camada in args.camadas:
        salvar_camada(uf, camada, args.recortar, args.incluir_cancelados)


if __name__ == "__main__":
    main()
