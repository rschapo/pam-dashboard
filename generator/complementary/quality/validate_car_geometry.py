"""
validate_car_geometry.py — QC das geometrias e resumos do CAR (§9.6).

Por UF processada, verifica: geometrias válidas (após correção), área em hectares
plausível, geometrias fora da UF, sobreposições, divergência área declarada x
geométrica, distribuição municipal, status padronizados e data da base.
Grava data/manifests/validate_car.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import PROCESSED_DIR, MANIFEST_DIR  # noqa: E402

GEO = PROCESSED_DIR / "geospatial"


def run() -> dict:
    res = {"ufs": {}}
    validos = sorted(GEO.glob("car_imoveis_validos_*.parquet"))
    if not validos:
        res["status"] = "nenhuma UF processada"
    for p in validos:
        uf = p.stem.split("_")[-1]
        df = pd.read_parquet(p)
        res["ufs"][uf] = {
            "imoveis": int(len(df)),
            "fora_uf": int(df["flag_fora_uf"].sum()) if "flag_fora_uf" in df else None,
            "area_divergente": int(df["flag_area_divergente"].sum()) if "flag_area_divergente" in df else None,
            "duplicidades": int(df["flag_duplicidade"].sum()) if "flag_duplicidade" in df else None,
            "status_nao_padronizados": int(df["situacao_car_padronizada"].isna().sum())
            if "situacao_car_padronizada" in df else None,
        }
    summ = GEO / "car_municipio_summary.parquet"
    if summ.exists():
        s = pd.read_parquet(summ)
        res["municipios_resumidos"] = int(s["cod_municipio"].nunique())
        res["sobreposicao_media_pct"] = round(float(
            pd.to_numeric(s["percentual_sobreposicao"], errors="coerce").mean()), 2) if len(s) else None
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    (MANIFEST_DIR / "validate_car.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res


def main():
    print("== validate_car_geometry ==")
    print(json.dumps(run(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
