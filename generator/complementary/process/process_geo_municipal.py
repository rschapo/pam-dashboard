"""
process_geo_municipal.py — Malha municipal (coroplético MUNICIPAL do dashboard).

Converte data/raw/ibge/malha_municipios.gpkg (IBGE, EPSG:4326, camada
"malha_municipios", campo "codarea") em public/data/geo_mun.json — mesmo
padrão de geo_uf.json / geo_mic.json já publicados (FeatureCollection leve,
pronta para Leaflet), agora com uma propriedade-chave `cod_ibge` (7 dígitos).

Fonte: já baixada (não requer rede) — ver BRIEFING_DADOS_PAM_IBGE.md item A.

Uso:
  python process_geo_municipal.py [--tolerancia 0.0015] [--uf GO,TO]

  --uf recorta para os estados informados (siglas separadas por vírgula);
       sem --uf, gera o Brasil inteiro (5.570 municípios).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import RAW_DIR, PROJECT_ROOT, cod_mun7, uf_from_cod, write_manifest  # noqa: E402

GPKG_PATH = RAW_DIR / "ibge" / "malha_municipios.gpkg"
OUT_PATH = PROJECT_ROOT / "public" / "data" / "geo_mun.json"


def build(tolerancia: float, ufs: list[str] | None):
    import geopandas as gpd

    if not GPKG_PATH.exists():
        raise SystemExit(
            f"Não encontrado: {GPKG_PATH}\n"
            "Baixe a malha municipal (API IBGE Malhas v3, intrarregiao=municipio) "
            "ou copie o gpkg para data/raw/ibge/."
        )

    print(f"Lendo {GPKG_PATH.name} …")
    gdf = gpd.read_file(GPKG_PATH, engine="pyogrio")
    gdf["cod_ibge"] = gdf["codarea"].map(cod_mun7)
    gdf = gdf[gdf["cod_ibge"].notna()].copy()
    gdf["uf"] = gdf["cod_ibge"].map(uf_from_cod)

    rejeitados = int(gdf["uf"].isna().sum())
    if rejeitados:
        print(f"  [AVISO] {rejeitados} feature(s) sem UF identificável — descartadas")
        gdf = gdf[gdf["uf"].notna()].copy()

    if ufs:
        antes = len(gdf)
        gdf = gdf[gdf["uf"].isin(ufs)].copy()
        print(f"  Recorte --uf {','.join(ufs)}: {antes} -> {len(gdf)} municípios")

    print(f"  Simplificando geometria (tolerância {tolerancia}°) …")
    gdf["geometry"] = gdf["geometry"].simplify(tolerancia, preserve_topology=True)

    gdf = gdf[["cod_ibge", "uf", "geometry"]].sort_values("cod_ibge").reset_index(drop=True)
    return gdf


def main():
    ap = argparse.ArgumentParser(description="Gera public/data/geo_mun.json (coroplético municipal)")
    ap.add_argument("--tolerancia", type=float, default=0.0015,
                     help="Tolerância de simplificação em graus (padrão 0.0015 ~ 165m no equador)")
    ap.add_argument("--uf", type=str, default=None,
                     help="Siglas de UF separadas por vírgula (padrão: Brasil inteiro)")
    args = ap.parse_args()
    ufs = [u.strip().upper() for u in args.uf.split(",")] if args.uf else None

    gdf = build(args.tolerancia, ufs)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # geometry.__geo_interface__ evita casas decimais excessivas do to_json() padrão
    fc = json.loads(gdf.to_json(drop_id=True))
    OUT_PATH.write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    size_mb = OUT_PATH.stat().st_size / 1_048_576
    print(f"  Municípios: {len(gdf):,}")
    print(f"  geo_mun.json: {size_mb:.1f} MB -> {OUT_PATH}")

    write_manifest(
        "geo_mun",
        source="IBGE Malhas (gpkg pré-baixado)",
        reference_date=None,
        source_files=[str(GPKG_PATH)],
        row_count=len(gdf),
        municipality_count=gdf["cod_ibge"].nunique(),
        output_files=[str(OUT_PATH)],
        extra={"tolerancia_simplificacao_graus": args.tolerancia,
               "recorte_uf": ufs or "Brasil"},
    )
    print("Concluído.")


if __name__ == "__main__":
    main()
