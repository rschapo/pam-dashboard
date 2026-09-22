"""
download_ibge_geography.py — Coleta a malha político-administrativa do IBGE.

Roda NA MÁQUINA DO USUÁRIO (rede aberta). Grava em data/raw/ibge/:
  * municipios.csv       — municípios + hierarquia (localidades API)
  * malha_municipios.gpkg — geometrias municipais (malhas API v3) [opcional --malha]

A área territorial (AR) NÃO vem da API de localidades: baixe a planilha oficial
"Áreas Territoriais" do IBGE e salve como data/raw/ibge/areas_municipios.xlsx
(o process_geography.py a lê se presente; caso contrário area = null).

Uso:
  python download_ibge_geography.py            # só municipios.csv
  python download_ibge_geography.py --malha    # também baixa geometrias (mais pesado)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import (  # noqa: E402
    RAW_DIR, API_LOCALIDADES, cod_mun7, require_local_network, write_manifest, today_iso,
)


def coletar_municipios() -> pd.DataFrame:
    import requests
    r = requests.get(f"{API_LOCALIDADES}/municipios", timeout=90)
    r.raise_for_status()
    linhas = []
    for m in r.json():
        imediata = m.get("regiao-imediata", {}) or {}
        intermediaria = imediata.get("regiao-intermediaria", {}) or {}
        micro = m.get("microrregiao", {}) or {}
        meso = micro.get("mesorregiao", {}) or {}
        uf = meso.get("UF", {}) or {}
        regiao = uf.get("regiao", {}) or {}
        linhas.append({
            "cod_ibge": cod_mun7(m["id"]),
            "nome_municipio": m["nome"],
            "cod_uf": uf.get("id"),
            "sigla_uf": uf.get("sigla"),
            "regiao": regiao.get("nome"),
            "cod_regiao_imediata": imediata.get("id"),
            "nome_regiao_imediata": imediata.get("nome"),
            "cod_regiao_intermediaria": intermediaria.get("id"),
            "nome_regiao_intermediaria": intermediaria.get("nome"),
            "cod_microrregiao": micro.get("id"),
            "nome_microrregiao": micro.get("nome"),
            "cod_mesorregiao": meso.get("id"),
            "nome_mesorregiao": meso.get("nome"),
        })
    return pd.DataFrame(linhas).sort_values("cod_ibge").reset_index(drop=True)


def coletar_malha(path: Path):
    """Baixa a malha municipal (GeoJSON) e grava como GeoPackage (requer geopandas)."""
    import requests
    try:
        import geopandas as gpd  # noqa: F401
    except ImportError:
        print("  [AVISO] geopandas ausente; pulei a malha. Instale para --malha.")
        return None
    url = "https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR?formato=application/vnd.geo+json&intrarregiao=municipio"
    print("  baixando malha municipal (pode demorar)…")
    r = requests.get(url, timeout=600)
    r.raise_for_status()
    import io
    import geopandas as gpd
    gdf = gpd.read_file(io.BytesIO(r.content))
    gdf.to_file(path, driver="GPKG")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--malha", action="store_true", help="também baixa geometrias municipais")
    args = ap.parse_args()
    require_local_network("IBGE geografia")

    outdir = RAW_DIR / "ibge"
    outdir.mkdir(parents=True, exist_ok=True)
    df = coletar_municipios()
    csv = outdir / "municipios.csv"
    df.to_csv(csv, sep=";", index=False, encoding="utf-8")
    outs = [str(csv)]
    print(f"  municipios.csv: {len(df):,} municípios")

    if args.malha:
        gpkg = coletar_malha(outdir / "malha_municipios.gpkg")
        if gpkg:
            outs.append(str(gpkg))

    write_manifest("raw_ibge_geography", source="IBGE Localidades/Malhas",
                   reference_date=today_iso(), output_files=outs,
                   row_count=len(df), municipality_count=df["cod_ibge"].nunique())


if __name__ == "__main__":
    main()
