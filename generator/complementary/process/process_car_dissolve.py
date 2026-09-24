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

Duas filas podem rodar juntas — as camadas leves e a APP, por exemplo. A
gravação de cada UF é feita sob trava de arquivo, para que uma não apague a
camada que a outra acabou de gravar.

A Bahia tem medidas compostas, porque o CEFIR registra o imóvel de outro jeito
(ver docs/CAR_LIMITATIONS.md): vegetação nativa, reserva legal e APP são fatias
disjuntas, e não existe área consolidada para imóvel privado. --compostas gera
car_ambiental_composta_BA com a vegetação nativa comparável ao padrão nacional
e a área de atividade produtiva declarada.

Uso:
  python process_car_dissolve.py --uf MT
  python process_car_dissolve.py --uf MT --camadas uso_restrito   # teste rápido
  python process_car_dissolve.py --pendentes [--camadas ...]
  python process_car_dissolve.py --compostas --uf BA
  python process_car_dissolve.py --uf MT --incluir-cancelados     # método antigo
  python process_car_dissolve.py --pendentes --camadas app --teto-mb 700
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
    return partes[0] if len(partes) == 1 else union_all(partes)


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
            "sem_municipio": 0, "inicio": time.time()}


def _medir_fontes(fontes: list[Fonte], subtrair: list[Fonte] | None = None,
                  recortar: bool = False) -> tuple[dict[str, float], dict]:
    """Área (ha) por município da união das fontes, menos a união de subtrair."""
    from shapely import union_all
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
            u = union_all(lista)
            if tirar.get(cod):
                u = u.difference(union_all(tirar[cod]))
            if malha is not None and cod in malha.index:
                u = u.intersection(malha.loc[cod])
            areas[cod] = u.area / 10_000.0
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
               ("descartadas", "sem área"), ("sem_municipio", "sem município"))
              if est[k]]
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


def _executar(tarefas: list[tuple[str, str, Callable]]):
    """Roda uma lista de (uf, nome, função), registrando cada uma; falha não para a fila."""
    import traceback
    total, falhas, t0 = len(tarefas), 0, time.time()
    for i, (uf, nome, fazer) in enumerate(tarefas, 1):
        t1 = time.time()
        anotar(f"[{i}/{total}] {uf}/{nome} iniciada")
        try:
            fazer()
            anotar(f"[{i}/{total}] {uf}/{nome} ok em {(time.time() - t1) / 60:.0f} min")
        except Exception as e:
            falhas += 1
            anotar(f"[{i}/{total}] {uf}/{nome} FALHOU: {type(e).__name__}: {e}")
            with open(REGISTRO, "a", encoding="utf-8") as f:
                f.write(traceback.format_exc() + "\n")
    anotar(f"fila concluída em {(time.time() - t0) / 3600:.1f} h, {falhas} falha(s)")


def rodar_pendentes(recortar: bool, quais: list[str] | None = None,
                    incluir_cancelados: bool = False):
    met = metodo(recortar, incluir_cancelados)
    _invalidar_metodo_antigo(met)
    pend = pendencias(quais, met)
    if not pend:
        print("[CAR dissolve] nada pendente: tudo que está extraído já foi medido.")
        return
    total = sum(len(v) for v in pend.values())
    anotar(f"fila iniciada ({met}): {total} camada(s) em {len(pend)} UF(s): {', '.join(pend)}")
    _executar([(uf, c, (lambda uf=uf, c=c: salvar_camada(uf, c, recortar, incluir_cancelados)))
               for uf, camadas in pend.items() for c in camadas])


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
                    help="medidas compostas da UF (hoje só a Bahia)")
    ap.add_argument("--incluir-cancelados", action="store_true",
                    help="mantém cadastros cancelados (método anterior a 2026-09-23)")
    ap.add_argument("--teto-mb", type=int, default=TETO_MB,
                    help="MB de geometria por bloco de municípios; menor gasta menos "
                         "memória, e um município sozinho nunca é partido")
    args = ap.parse_args()
    TETO_MB = args.teto_mb

    if args.pendentes:
        # --camadas restringe a fila; sem ele, mede as cinco.
        escolhidas = args.camadas if args.camadas != CAMADAS else None
        rodar_pendentes(args.recortar, escolhidas, args.incluir_cancelados)
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
