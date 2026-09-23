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

A leitura é paginada porque uma camada pode passar de 2 GB por shapefile — o
SICAR fatia em _1.._N justamente por isso, e carregar tudo de uma vez estoura a
memória.

Uso:
  python process_car_dissolve.py --uf MT
  python process_car_dissolve.py --uf MT --camadas uso_restrito   # teste rápido
  python process_car_dissolve.py --uf MT --recortar               # + malha municipal
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import RAW_DIR, PROCESSED_DIR, CRS_AREA, cod_mun7, save_table  # noqa: E402

GEO = PROCESSED_DIR / "geospatial"
CAMADAS = ["area_consolidada", "vegetacao_nativa", "reserva_legal", "app", "uso_restrito"]
LOTE = 100_000


def _mun_do_car(v) -> str | None:
    m = re.search(r"-(\d{7})-", str(v))
    return cod_mun7(m.group(1)) if m else None


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


def dissolver_camada(uf: str, camada: str, recortar: bool) -> pd.Series | None:
    """Área dissolvida (ha) por município, para uma camada."""
    import geopandas as gpd
    import pyogrio
    from shapely import union_all, is_valid

    d = RAW_DIR / "car" / uf / camada
    arquivos = sorted(d.rglob("*.shp")) if d.exists() else []
    if not arquivos:
        return None

    # Acumula por município e só depois dissolve: unir em lotes parciais faria a
    # mesma área ser reunida várias vezes, que é justamente o que se quer evitar.
    por_municipio: dict[str, list] = {}
    lidas = 0
    t0 = time.time()
    for arq in arquivos:
        total = pyogrio.read_info(arq)["features"]
        for inicio in range(0, total, LOTE):
            g = pyogrio.read_dataframe(
                arq, columns=["cod_imovel"], skip_features=inicio, max_features=LOTE)
            g["cod_municipio"] = g["cod_imovel"].map(_mun_do_car)
            g = g[g["cod_municipio"].notna()]
            g = g.to_crs(CRS_AREA)
            for cod, sub in g.groupby("cod_municipio"):
                por_municipio.setdefault(cod, []).extend(
                    x for x in sub.geometry.values if x is not None and not x.is_empty)
            lidas += len(g)
        print(f"    {arq.name}: {total:,} feições lidas ({time.time() - t0:.0f}s)")

    if not por_municipio:
        return None

    malha = _malha_municipal(por_municipio.keys()) if recortar else None
    areas = {}
    invalidas = descartadas = 0
    for i, (cod, geoms) in enumerate(sorted(por_municipio.items()), 1):
        # O CAR traz polígonos com anel invertido e auto-interseção; o GEOS
        # aborta a união ao encontrá-los, então saneia antes de unir.
        saneadas = []
        for g in geoms:
            if is_valid(g):
                g = _so_area(g)
            else:
                invalidas += 1
                g = _sanear(g)
            if g is None:
                descartadas += 1
                continue
            saneadas.append(g)
        if not saneadas:
            continue
        u = union_all(saneadas)
        if malha is not None and cod in malha.index:
            u = u.intersection(malha.loc[cod])
        areas[cod] = u.area / 10_000.0
        if i % 25 == 0:
            print(f"    dissolvidos {i}/{len(por_municipio)} municípios "
                  f"({time.time() - t0:.0f}s)")
    print(f"  {camada}: {len(areas)} municípios, {sum(areas.values()):,.0f} ha "
          f"dissolvidos de {lidas:,} feições em {time.time() - t0:.0f}s"
          + (f" ({invalidas:,} geometrias saneadas)" if invalidas else "")
          + (f" ({descartadas:,} sem área, descartadas)" if descartadas else ""))
    return pd.Series(areas, name=f"{camada}_ha").rename_axis("cod_municipio")


def pendencias(quais: list[str] | None = None) -> dict[str, list[str]]:
    """UFs com camada extraída e ainda não medida, na ordem do mais barato."""
    from common import UFS
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
        if parquet_uf.exists():
            medidas = {c[:-3] for c in pd.read_parquet(parquet_uf).columns
                       if c.endswith("_ha")}
        falta = [c for c in extraidas if c not in medidas]
        if falta:
            # Peso do shapefile aproxima o custo; começar pelas leves devolve
            # resultado cedo e deixa as caras por último.
            falta.sort(key=lambda c: sum(f.stat().st_size for f in (base / c).rglob("*.shp")))
            out[uf] = falta
    return out


def rodar_pendentes(recortar: bool, quais: list[str] | None = None):
    pend = pendencias(quais)
    if not pend:
        print("[CAR dissolve] nada pendente: tudo que está extraído já foi medido.")
        return
    total = sum(len(v) for v in pend.values())
    print(f"[CAR dissolve] {total} camada(s) pendente(s) em {len(pend)} UF(s): "
          f"{', '.join(pend)}")
    # A fila roda por horas, quase sempre com a saída redirecionada; um pipe
    # segura tudo em buffer e uma falha no meio só apareceria no fim. O registro
    # em arquivo é escrito linha a linha e sobrevive a qualquer forma de disparo.
    registro = GEO / "car_dissolve_fila.log"

    def anotar(msg: str):
        linha = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
        print(linha, flush=True)
        with open(registro, "a", encoding="utf-8") as f:
            f.write(linha + "\n")

    anotar(f"fila iniciada: {total} camada(s) em {len(pend)} UF(s): {', '.join(pend)}")
    feito = falhas = 0
    t0 = time.time()
    for uf, camadas in pend.items():
        for camada in camadas:
            feito += 1
            t1 = time.time()
            anotar(f"[{feito}/{total}] {uf}/{camada} iniciada")
            try:
                salvar_camada(uf, camada, recortar)
                anotar(f"[{feito}/{total}] {uf}/{camada} ok em {(time.time() - t1) / 60:.0f} min")
            except Exception as e:
                # Uma UF problemática não pode derrubar a fila inteira.
                import traceback
                falhas += 1
                anotar(f"[{feito}/{total}] {uf}/{camada} FALHOU: {type(e).__name__}: {e}")
                with open(registro, "a", encoding="utf-8") as f:
                    f.write(traceback.format_exc() + "\n")
    anotar(f"fila concluída em {(time.time() - t0) / 3600:.1f} h, "
           f"{falhas} falha(s) — ver {registro.name}")


def salvar_camada(uf: str, camada: str, recortar: bool):
    """Mede uma camada e mescla no parquet da UF."""
    s = dissolver_camada(uf, camada, recortar)
    if s is None:
        print(f"  {camada}: ausente em data/raw/car/{uf}/")
        return
    out = s.to_frame().reset_index()
    out["uf"] = uf
    out["metodo"] = "dissolve+recorte" if recortar else "dissolve"
    _gravar(out, uf, recortar)


def _gravar(out, uf: str, recortar: bool):
    alvo = GEO / f"car_ambiental_dissolve_{uf}"
    anterior = alvo.with_suffix(".parquet")
    if anterior.exists():
        velho = pd.read_parquet(anterior)
        novas = [c for c in out.columns if c.endswith("_ha")]
        velho = velho.drop(columns=[c for c in novas if c in velho.columns])
        out = velho.drop(columns=["uf", "metodo"], errors="ignore").merge(
            out, on="cod_municipio", how="outer")
        out["uf"] = uf
        out["metodo"] = "dissolve+recorte" if recortar else "dissolve"
    colunas = ["cod_municipio"] + sorted(c for c in out.columns if c.endswith("_ha"))
    out = out[colunas + ["uf", "metodo"]]
    save_table(out, alvo)
    print(f"  [{uf}] {len(out)} municípios · "
          f"{', '.join(c[:-3] for c in colunas[1:])}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uf")
    ap.add_argument("--camadas", nargs="*", default=CAMADAS)
    ap.add_argument("--recortar", action="store_true",
                    help="intercepta com a malha municipal além de dissolver")
    ap.add_argument("--pendentes", action="store_true",
                    help="mede tudo que está extraído e ainda não foi medido")
    args = ap.parse_args()

    if args.pendentes:
        # --camadas restringe a fila; sem ele, mede as cinco.
        escolhidas = args.camadas if args.camadas != CAMADAS else None
        rodar_pendentes(args.recortar, escolhidas)
        return
    if not args.uf:
        raise SystemExit("informe --uf ou use --pendentes")
    uf = args.uf.upper()

    print(f"[CAR dissolve/{uf}] camadas: {', '.join(args.camadas)}")
    out = None
    for camada in args.camadas:
        s = dissolver_camada(uf, camada, args.recortar)
        if s is None:
            print(f"  {camada}: ausente em data/raw/car/{uf}/")
            continue
        out = s.to_frame() if out is None else out.join(s, how="outer")
    if out is None:
        raise SystemExit(f"Nenhuma camada encontrada em data/raw/car/{uf}/.")

    out = out.reset_index()
    out["uf"] = uf
    out["metodo"] = "dissolve+recorte" if args.recortar else "dissolve"

    # Cada camada leva dezenas de minutos, então normalmente se roda uma por vez.
    # Sem mesclar, a rodada seguinte apagaria as anteriores.
    alvo = GEO / f"car_ambiental_dissolve_{uf}"
    anterior = alvo.with_suffix(".parquet")
    if anterior.exists():
        velho = pd.read_parquet(anterior)
        novas = [c for c in out.columns if c.endswith("_ha")]
        velho = velho.drop(columns=[c for c in novas if c in velho.columns])
        out = velho.drop(columns=["uf", "metodo"], errors="ignore").merge(
            out, on="cod_municipio", how="outer")
        out["uf"] = uf
        out["metodo"] = "dissolve+recorte" if args.recortar else "dissolve"
    colunas = ["cod_municipio"] + sorted(c for c in out.columns if c.endswith("_ha"))
    out = out[colunas + ["uf", "metodo"]]
    save_table(out, alvo)
    print(f"[CAR dissolve/{uf}] {len(out)} municípios · "
          f"{', '.join(c[:-3] for c in colunas[1:])} -> {alvo}.parquet")


if __name__ == "__main__":
    main()
