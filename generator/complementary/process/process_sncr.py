"""
process_sncr.py — Imóveis rurais do SNCR: base tratada, válida, rejeições e
resumo municipal (Etapa 1, §6.5–6.7).

Lê o bruto por UF em data/raw/sncr/<uf>/ (CSV/Shapefile), aplica privacidade
(seção 2.3: sem CPF/CNPJ/nome; identificador de imóvel vira hash), classifica por
módulo fiscal (dim_modulo_fiscal) e agrega por município com Gini/percentis.

Saídas:
  data/processed/municipality/sncr_imoveis_validos.parquet
  data/processed/municipality/sncr_municipio_summary.parquet | .csv
  data/interim/sncr/sncr_rejeicoes.parquet
  data/manifests/sncr_*.json

Regras: NÃO excluir inconsistências (vão p/ rejeições); ausência = null, nunca 0;
distribuição por QUANTIDADE e por ÁREA são indicadores distintos (ambos calculados).
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # p/ importar _stats via orquestrador
from common import (  # noqa: E402
    RAW_DIR, INTERIM_DIR, PROCESSED_DIR, cod_mun7, uf_from_cod,
    save_table, write_manifest,
)
from _stats import resumo_area, faixa_mf, FAIXAS_MF_LEGAL  # noqa: E402

AREA_EXTREMA_HA = 500_000

COLS_VALIDAS = ["id_imovel_hash", "cod_municipio", "uf", "area_total_ha",
                "situacao_cadastral", "data_referencia", "fonte",
                "numero_modulos_fiscais", "faixa_modulo_analitica", "faixa_modulo_legal",
                "flag_area_zero", "flag_area_negativa", "flag_municipio_invalido",
                "flag_duplicidade"]


def _hash_id(raw_id) -> str:
    return hashlib.sha256(f"SNCR::{raw_id}".encode()).hexdigest()[:24]


def _read_uf(uf: str) -> pd.DataFrame:
    """Lê os arquivos de uma UF. Suporta CSV; para Shapefile requer geopandas.
    Espera identificar colunas de id de imóvel, código municipal e área total (ha)."""
    d = RAW_DIR / "sncr" / uf
    if not d.exists():
        return pd.DataFrame()
    frames = []
    for p in d.glob("*.csv"):
        frames.append(pd.read_csv(p, sep=None, engine="python", dtype=str))
    for p in list(d.glob("*.shp")) + list(d.glob("*.gpkg")):
        try:
            import geopandas as gpd
            g = gpd.read_file(p)
            frames.append(pd.DataFrame(g.drop(columns=g.geometry.name)))
        except Exception as e:  # pragma: no cover
            print(f"  [AVISO] {p.name}: {e}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _pick(cols, *keys):
    for c in cols:
        cl = str(c).lower()
        if all(k in cl for k in keys):
            return c
    return None


def _tratar_uf(uf: str, mf_map: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = _read_uf(uf)
    if raw.empty:
        return pd.DataFrame(), pd.DataFrame()
    cols = list(raw.columns)
    c_id = _pick(cols, "imovel") or _pick(cols, "codigo", "imovel") or _pick(cols, "ccir") or cols[0]
    c_cod = _pick(cols, "municipio", "cod") or _pick(cols, "cod", "ibge") or _pick(cols, "municipio")
    c_area = _pick(cols, "area", "total") or _pick(cols, "area")

    validos, rejeitados = [], []
    vistos = set()
    for _, r in raw.iterrows():
        cod = cod_mun7(r[c_cod]) if c_cod else None
        try:
            area = float(str(r[c_area]).replace(".", "").replace(",", ".")) if c_area else None
        except (TypeError, ValueError):
            area = None
        hid = _hash_id(r[c_id])
        f_zero = area == 0
        f_neg = area is not None and area < 0
        f_mun_inval = (cod is None) or (uf_from_cod(cod) != uf)
        f_dup = hid in vistos
        vistos.add(hid)

        mf = mf_map.get(cod)
        n_mf = (area / mf) if (area and mf and area > 0) else None
        rec = {
            "id_imovel_hash": hid, "cod_municipio": cod, "uf": uf,
            "area_total_ha": area, "situacao_cadastral": r.get(_pick(cols, "situacao")) if _pick(cols, "situacao") else None,
            "data_referencia": None, "fonte": "INCRA/SNCR",
            "numero_modulos_fiscais": round(n_mf, 4) if n_mf is not None else None,
            "faixa_modulo_analitica": faixa_mf(n_mf),
            "faixa_modulo_legal": faixa_mf(n_mf, FAIXAS_MF_LEGAL),
            "flag_area_zero": bool(f_zero), "flag_area_negativa": bool(f_neg),
            "flag_municipio_invalido": bool(f_mun_inval), "flag_duplicidade": bool(f_dup),
            "flag_area_extrema": bool(area is not None and area > AREA_EXTREMA_HA),
        }
        if f_neg or f_mun_inval or area is None:
            rejeitados.append(rec)
        else:
            validos.append(rec)
    return pd.DataFrame(validos), pd.DataFrame(rejeitados)


def _summary(validos: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for cod, g in validos.groupby("cod_municipio"):
        areas = g["area_total_ha"]
        base = {"cod_municipio": cod,
                "quantidade_imoveis_total": len(g),
                "quantidade_imoveis_validos": int((~g["flag_area_zero"]).sum()),
                **resumo_area(areas)}
        mf = pd.to_numeric(g["numero_modulos_fiscais"], errors="coerce")
        base["modulos_fiscais_media"] = round(float(mf.mean()), 4) if mf.notna().any() else None
        base["modulos_fiscais_mediana"] = round(float(mf.median()), 4) if mf.notna().any() else None
        # distribuição por QUANTIDADE
        fa = g["faixa_modulo_analitica"]
        base["quantidade_ate_1_mf"] = int((fa == "ate_1_mf").sum())
        base["quantidade_1_2_mf"] = int((fa == "mais_1_ate_2_mf").sum())
        base["quantidade_2_4_mf"] = int((fa == "mais_2_ate_4_mf").sum())
        fl = g["faixa_modulo_legal"]
        q_ate4 = int((fl == "ate_4_mf").sum())
        q_4_15 = int((fl == "mais_4_ate_15_mf").sum())
        q_ac15 = int((fl == "mais_15_mf").sum())
        base["quantidade_4_15_mf"] = q_4_15
        base["quantidade_acima_15_mf"] = q_ac15
        n = max(1, len(g))
        base["percentual_imoveis_ate_4_mf"] = round(100.0 * q_ate4 / n, 2)
        base["percentual_imoveis_4_15_mf"] = round(100.0 * q_4_15 / n, 2)
        base["percentual_imoveis_acima_15_mf"] = round(100.0 * q_ac15 / n, 2)
        # distribuição por ÁREA (indicador distinto do de quantidade)
        area_tot = float(pd.to_numeric(areas, errors="coerce").fillna(0).sum()) or 1.0
        a_ate4 = float(pd.to_numeric(g.loc[fl == "ate_4_mf", "area_total_ha"], errors="coerce").sum())
        a_4_15 = float(pd.to_numeric(g.loc[fl == "mais_4_ate_15_mf", "area_total_ha"], errors="coerce").sum())
        a_ac15 = float(pd.to_numeric(g.loc[fl == "mais_15_mf", "area_total_ha"], errors="coerce").sum())
        base["percentual_area_ate_4_mf"] = round(100.0 * a_ate4 / area_tot, 2)
        base["percentual_area_4_15_mf"] = round(100.0 * a_4_15 / area_tot, 2)
        base["percentual_area_acima_15_mf"] = round(100.0 * a_ac15 / area_tot, 2)
        base["data_referencia"] = None
        rows.append(base)
    return pd.DataFrame(rows).sort_values("cod_municipio")


def _read_mf() -> dict:
    p = PROCESSED_DIR / "dimensions" / "dim_modulo_fiscal.parquet"
    if not p.exists():
        print("  [AVISO] dim_modulo_fiscal ausente — número de módulos ficará null.")
        return {}
    d = pd.read_parquet(p)
    return {r.cod_municipio: r.modulo_fiscal_ha for r in d.itertuples() if r.modulo_fiscal_ha}


def main(ufs=None):
    from common import UFS
    ufs = ufs or UFS
    mf_map = _read_mf()
    val_frames, rej_frames = [], []
    for uf in ufs:
        v, rj = _tratar_uf(uf, mf_map)
        if not v.empty:
            val_frames.append(v)
        if not rj.empty:
            rej_frames.append(rj)
        if not v.empty or not rj.empty:
            print(f"  {uf}: {len(v):,} válidos · {len(rj):,} rejeições")

    if not val_frames and not rej_frames:
        print("[SNCR] Nenhum bruto encontrado em data/raw/sncr/<uf>/. "
              "Rode download/download_sncr.py e coloque os arquivos.")
        return

    validos = pd.concat(val_frames, ignore_index=True) if val_frames else pd.DataFrame(columns=COLS_VALIDAS)
    rejeicoes = pd.concat(rej_frames, ignore_index=True) if rej_frames else pd.DataFrame()
    summary = _summary(validos) if not validos.empty else pd.DataFrame()

    outs = save_table(validos, PROCESSED_DIR / "municipality" / "sncr_imoveis_validos", csv=False)
    outs += save_table(summary, PROCESSED_DIR / "municipality" / "sncr_municipio_summary")
    (INTERIM_DIR / "sncr").mkdir(parents=True, exist_ok=True)
    rej_path = INTERIM_DIR / "sncr" / "sncr_rejeicoes.parquet"
    rejeicoes.to_parquet(rej_path, index=False)

    write_manifest("sncr_municipio_summary", source="SNCR/Incra",
                   reference_date=None, source_files=[str(RAW_DIR / "sncr")],
                   row_count=len(validos), municipality_count=validos["cod_municipio"].nunique() if not validos.empty else 0,
                   rejected_rows=len(rejeicoes), output_files=outs + [str(rej_path)])
    print(f"[SNCR] válidos={len(validos):,} · rejeições={len(rejeicoes):,} · municípios={summary['cod_municipio'].nunique() if not summary.empty else 0}")


if __name__ == "__main__":
    main()
