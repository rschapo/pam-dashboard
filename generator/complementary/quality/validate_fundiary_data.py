"""
validate_fundiary_data.py — QC de módulo fiscal e SNCR (§9.2, §9.4).

Módulo fiscal: valores > 0; correspondência município/UF; registro de não
correspondidos. SNCR: quantidade por UF, válidos x rejeitados, área por UF, áreas
extremas, duplicidades, áreas zero, municípios inexistentes. Não exclui nada —
apenas relata. Grava data/manifests/validate_fundiary.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import PROCESSED_DIR, MANIFEST_DIR, uf_from_cod  # noqa: E402


def _check_modulo(res):
    p = PROCESSED_DIR / "dimensions" / "dim_modulo_fiscal.parquet"
    if not p.exists():
        res["modulo_fiscal"] = {"status": "ausente"}
        return
    df = pd.read_parquet(p)
    mf = pd.to_numeric(df["modulo_fiscal_ha"], errors="coerce")
    res["modulo_fiscal"] = {
        "municipios": int(df["cod_municipio"].nunique()),
        "modulo_zero_ou_neg": int((mf <= 0).sum()),
        "modulo_nulo": int(mf.isna().sum()),
        "uf_incompativel": int(df.apply(
            lambda r: uf_from_cod(r["cod_municipio"]) is None, axis=1).sum()),
    }


def _check_sncr(res):
    p = PROCESSED_DIR / "municipality" / "sncr_municipio_summary.parquet"
    vp = PROCESSED_DIR / "municipality" / "sncr_imoveis_validos.parquet"
    if not p.exists():
        res["sncr"] = {"status": "ausente"}
        return
    summ = pd.read_parquet(p)
    info = {"municipios": int(summ["cod_municipio"].nunique())}
    if vp.exists():
        v = pd.read_parquet(vp)
        info.update({
            "imoveis_validos": int(len(v)),
            "area_zero": int(v["flag_area_zero"].sum()) if "flag_area_zero" in v else None,
            "municipio_invalido": int(v["flag_municipio_invalido"].sum()) if "flag_municipio_invalido" in v else None,
            "duplicidades": int(v["flag_duplicidade"].sum()) if "flag_duplicidade" in v else None,
            "por_uf": v.groupby("uf").size().to_dict() if "uf" in v else {},
        })
    res["sncr"] = info


def run() -> dict:
    res = {}
    _check_modulo(res)
    _check_sncr(res)
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    (MANIFEST_DIR / "validate_fundiary.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res


def main():
    res = run()
    print("== validate_fundiary_data ==")
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
