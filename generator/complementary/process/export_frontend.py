"""
export_frontend.py — Etapa 3: gera os JSONs de front-end das bases complementares.

Converte os Parquet de data/processed/ em JSONs COMPACTOS, gravados em
`data/frontend/` — pasta SEPARADA de `public/data/` (não altera o dashboard em
produção; a integração real é feita depois, ver docs/INTEGRATION_PLAN.md).

Gera:
  perfil_rural.json  — 1 registro por município: identidade + indicadores agregados
                       (fundiário/produtivo/ambiental preenchidos conforme existirem).
  car_profile.json   — resumo do CAR por município (se car_municipio_summary existir).
  land_use.json      — uso do solo por município/ano (se mapbiomas_municipio existir),
                       agregado por grupo analítico e particionável por UF.

Estrutura do perfil_rural.json (compacta, alinhada ao padrão do dashboard):
  {
    "gerado_em": "...", "cobertura": {campo: n_municipios_preenchidos},
    "ufs_info": {uf: nome_uf},
    "campos": [ ...ordem dos campos... ],
    "mun": { "<cod_municipio>": {campo: valor, ...} }
  }

Nada aqui depende de rede.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import (  # noqa: E402
    PROCESSED_DIR, DATA_DIR, UF_NAMES, now_iso, write_manifest,
)

FRONTEND_DIR = DATA_DIR / "frontend"


def _load(rel):
    p = (PROCESSED_DIR / rel).with_suffix(".parquet")
    return pd.read_parquet(p) if p.exists() else None


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, (pd.Timestamp,)):
        return str(v)
    try:
        import numpy as np
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return None if math.isnan(float(v)) else float(v)
        if isinstance(v, (np.bool_,)):
            return bool(v)
    except ImportError:
        pass
    return v


def build_perfil_rural() -> dict:
    dim = _load("dimensions/dim_municipio")
    if dim is None:
        raise SystemExit("dim_municipio ausente. Rode process_geography.py primeiro.")

    # base de identidade
    cols_id = ["cod_municipio", "nome_municipio", "uf", "nome_regiao",
               "cod_microrregiao", "cod_mesorregiao", "area_municipal_ha",
               "flag_sem_producao_pam", "flag_sem_producao_ppm"]
    base = dim[[c for c in cols_id if c in dim.columns]].copy()

    # camadas agregadas (quando existirem) — merge à esquerda pela chave
    prof = _load("municipality/rural_profile_stage2")
    if prof is None:
        prof = _load("municipality/rural_profile_stage1")
    if prof is not None:
        extra = [c for c in prof.columns if c not in ("uf",) and c != "cod_municipio"]
        base = base.merge(prof[["cod_municipio"] + extra], on="cod_municipio", how="left")

    # deriva presença (mais legível que a flag "sem_producao")
    if "flag_sem_producao_pam" in base:
        base["tem_pam"] = base["flag_sem_producao_pam"].map(
            lambda x: (not x) if x is not None else None)
    if "flag_sem_producao_ppm" in base:
        base["tem_ppm"] = base["flag_sem_producao_ppm"].map(
            lambda x: (not x) if x is not None else None)
    base = base.drop(columns=[c for c in ("flag_sem_producao_pam", "flag_sem_producao_ppm") if c in base])

    campos = [c for c in base.columns if c != "cod_municipio"]
    cobertura = {c: int(base[c].notna().sum()) for c in campos}
    mun = {}
    for r in base.itertuples(index=False):
        d = dict(zip(base.columns, r))
        cod = d.pop("cod_municipio")
        mun[cod] = {k: _clean(v) for k, v in d.items()}

    ufs_info = {uf: UF_NAMES[uf] for uf in sorted(base["uf"].dropna().unique())}
    return {"gerado_em": now_iso(), "cobertura": cobertura, "ufs_info": ufs_info,
            "campos": campos, "n_municipios": len(mun), "mun": mun}


def build_car_profile() -> dict | None:
    car = _load("geospatial/car_municipio_summary")
    if car is None:
        return None
    mun = {}
    for r in car.itertuples(index=False):
        d = dict(zip(car.columns, r))
        cod = d.pop("cod_municipio")
        mun[cod] = {k: _clean(v) for k, v in d.items()}
    return {"gerado_em": now_iso(), "n_municipios": len(mun), "mun": mun}


def build_land_use() -> dict | None:
    mb = _load("municipality/mapbiomas_municipio")
    if mb is None or mb.empty:
        return None
    ano = int(mb["ano"].max())
    cur = mb[mb["ano"] == ano]
    piv = cur.pivot_table(index="cod_municipio", columns="grupo_analitico",
                          values="area_ha", aggfunc="sum")
    mun = {cod: {g: _clean(v) for g, v in row.items()} for cod, row in piv.iterrows()}
    return {"gerado_em": now_iso(), "ano": ano, "grupos": list(piv.columns), "mun": mun}


def _write(name, obj):
    FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
    p = FRONTEND_DIR / name
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    mb = p.stat().st_size / 1_048_576
    print(f"  {name}: {obj.get('n_municipios', len(obj.get('mun', {})))} municípios · {mb:.2f} MB")
    return str(p)


def main():
    outs = []
    outs.append(_write("perfil_rural.json", build_perfil_rural()))
    car = build_car_profile()
    if car:
        outs.append(_write("car_profile.json", car))
    lu = build_land_use()
    if lu:
        outs.append(_write("land_use.json", lu))
    write_manifest("frontend_json", source="Composição das bases complementares (Parquet)",
                   reference_date=None, output_files=outs)
    print(f"[FRONTEND] {len(outs)} JSON(s) em data/frontend/ (separado de public/data)")


if __name__ == "__main__":
    main()
