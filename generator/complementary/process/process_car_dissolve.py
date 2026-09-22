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


def dissolver_camada(uf: str, camada: str, recortar: bool) -> pd.Series | None:
    """Área dissolvida (ha) por município, para uma camada."""
    import geopandas as gpd
    import pyogrio
    from shapely import union_all, make_valid, is_valid

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
    invalidas = 0
    for i, (cod, geoms) in enumerate(sorted(por_municipio.items()), 1):
        # O CAR traz polígonos com anel invertido e auto-interseção; o GEOS
        # aborta a união ao encontrá-los, então saneia antes de unir.
        saneadas = []
        for g in geoms:
            if not is_valid(g):
                g = make_valid(g)
                invalidas += 1
            saneadas.append(g)
        u = union_all(saneadas)
        if malha is not None and cod in malha.index:
            u = u.intersection(malha.loc[cod])
        areas[cod] = u.area / 10_000.0
        if i % 25 == 0:
            print(f"    dissolvidos {i}/{len(por_municipio)} municípios "
                  f"({time.time() - t0:.0f}s)")
    print(f"  {camada}: {len(areas)} municípios, {sum(areas.values()):,.0f} ha "
          f"dissolvidos de {lidas:,} feições em {time.time() - t0:.0f}s"
          + (f" ({invalidas:,} geometrias saneadas)" if invalidas else ""))
    return pd.Series(areas, name=f"{camada}_ha").rename_axis("cod_municipio")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uf", required=True)
    ap.add_argument("--camadas", nargs="*", default=CAMADAS)
    ap.add_argument("--recortar", action="store_true",
                    help="intercepta com a malha municipal além de dissolver")
    args = ap.parse_args()
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
    alvo = GEO / f"car_ambiental_dissolve_{uf}"
    save_table(out, alvo)
    print(f"[CAR dissolve/{uf}] {len(out)} municípios -> {alvo}.parquet")


if __name__ == "__main__":
    main()
