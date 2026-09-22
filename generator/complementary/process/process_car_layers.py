"""
process_car_layers.py — Camadas ambientais do CAR por município (Etapa 2, §7.6–7.7).

Agrega, por município, as camadas ambientais do SICAR presentes em
data/raw/car/<uf>/<camada>/ (subpastas: area_consolidada, vegetacao_nativa,
reserva_legal, app, uso_restrito). Cada shapefile do SICAR traz `cod_imovel`
(com o código IBGE embutido: UF-<7díg>-<hash>), então o município é atribuído
direto pelo código — sem interseção geométrica pesada. A área é a GEOMÉTRICA
(EPSG:5880), somada por município (base "bruta" por tema; sobreposições entre
imóveis do mesmo tema são pequenas e ficam documentadas).

Saídas:
  data/processed/geospatial/car_ambiental_municipio_<UF>.parquet|.csv
  + mescla as colunas ambientais em car_municipio_summary.parquet|.csv

Uso:
  python process_car_layers.py --uf AC
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import (  # noqa: E402
    RAW_DIR, PROCESSED_DIR, CRS_AREA, CRS_STORAGE, cod_mun7, write_manifest,
)

GEO = PROCESSED_DIR / "geospatial"
# subpasta da camada -> (coluna de área, coluna de percentual)
CAMADAS = {
    "area_consolidada": ("area_consolidada_ha", "percentual_area_consolidada"),
    "vegetacao_nativa": ("vegetacao_nativa_ha", "percentual_vegetacao_nativa"),
    "reserva_legal":    ("reserva_legal_ha",    "percentual_reserva_legal"),
    "app":              ("app_ha",              "percentual_app"),
    "uso_restrito":     ("uso_restrito_ha",     None),
}


def _mun_from_carid(v):
    m = re.search(r"-(\d{7})-", str(v))
    return cod_mun7(m.group(1)) if m else None


def _area_por_municipio(uf: str, camada: str) -> pd.Series | None:
    """Soma a área geométrica (ha, EPSG:5880) da camada por município."""
    import geopandas as gpd
    d = RAW_DIR / "car" / uf / camada
    files = sorted(d.rglob("*.shp")) if d.exists() else []
    if not files:
        return None
    parts = [gpd.read_file(f) for f in files]
    g = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=parts[0].crs)
    if g.crs is None:
        g.set_crs(CRS_STORAGE, inplace=True)
    idcol = next((c for c in g.columns if c.lower() == "cod_imovel"), None)
    g["cod_municipio"] = g[idcol].map(_mun_from_carid) if idcol else None
    g["area_ha"] = g.to_crs(CRS_AREA).geometry.area / 10_000.0
    return g.groupby("cod_municipio")["area_ha"].sum().round(4)


def build(uf: str) -> pd.DataFrame:
    out = None
    presentes = []
    for camada, (col, _pct) in CAMADAS.items():
        s = _area_por_municipio(uf, camada)
        if s is None:
            continue
        presentes.append(camada)
        s = s.rename(col)
        out = s.to_frame() if out is None else out.join(s, how="outer")
        print(f"  {camada}: {int(s.notna().sum())} municípios, {s.sum():,.0f} ha")
    if out is None:
        raise SystemExit(f"Nenhuma camada ambiental encontrada em data/raw/car/{uf}/.")
    out = out.reset_index()

    # percentuais sobre a área municipal (dim_municipio)
    dimp = PROCESSED_DIR / "dimensions" / "dim_municipio.parquet"
    if dimp.exists():
        dim = pd.read_parquet(dimp)[["cod_municipio", "area_municipal_ha"]]
        out = out.merge(dim, on="cod_municipio", how="left")
        for camada, (col, pct) in CAMADAS.items():
            if pct and col in out.columns:
                out[pct] = (out[col] / out["area_municipal_ha"] * 100).round(2)
        out = out.drop(columns="area_municipal_ha")
    out["uf"] = uf
    return out, presentes


def _merge_summary(amb: pd.DataFrame):
    """Acrescenta as colunas ambientais ao car_municipio_summary (por município)."""
    p = GEO / "car_municipio_summary.parquet"
    if not p.exists():
        print("  [AVISO] car_municipio_summary ausente — rode process_car.py --uf primeiro.")
        return
    summ = pd.read_parquet(p)
    novos = [c for c in amb.columns if c not in ("uf",)]
    summ = summ.drop(columns=[c for c in novos if c != "cod_municipio" and c in summ.columns], errors="ignore")
    summ = summ.merge(amb[novos], on="cod_municipio", how="left")
    summ.to_parquet(p, index=False)
    summ.to_csv(p.with_suffix(".csv"), sep=";", index=False, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uf", required=True)
    args = ap.parse_args()
    print(f"[CAR ambiental/{args.uf}] agregando camadas …")
    amb, presentes = build(args.uf)
    GEO.mkdir(parents=True, exist_ok=True)
    base = GEO / f"car_ambiental_municipio_{args.uf}"
    amb.to_parquet(base.with_suffix(".parquet"), index=False)
    amb.to_csv(base.with_suffix(".csv"), sep=";", index=False, encoding="utf-8")
    _merge_summary(amb)
    write_manifest(f"car_ambiental_{args.uf}", source="SICAR — camadas ambientais",
                   reference_date=None, row_count=len(amb),
                   municipality_count=amb["cod_municipio"].nunique(),
                   warnings=[f"camadas presentes: {', '.join(presentes)}"],
                   output_files=[str(base.with_suffix('.parquet'))])
    print(f"[CAR ambiental/{args.uf}] {len(amb)} municípios · camadas: {', '.join(presentes)}")


if __name__ == "__main__":
    main()
