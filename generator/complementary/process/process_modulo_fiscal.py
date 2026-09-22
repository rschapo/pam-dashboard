"""
process_modulo_fiscal.py — dim_modulo_fiscal (Etapa 1, §6.2).

Lê o bruto do INCRA (data/raw/incra/modulo_fiscal_municipios.{csv,xlsx}) e produz
a dimensão de módulo fiscal por município, casada ao cod_municipio (7 díg).

Junção robusta (§6.2): quando a fonte trouxer cod IBGE, usa-o direto; quando só
houver nome+UF, casa por (nome normalizado, UF) contra dim_municipio, com tabela
de exceções (config/modulo_fiscal_excecoes.csv) para os não correspondidos. NUNCA
casa só por nome.

Saídas:
  data/processed/dimensions/dim_modulo_fiscal.parquet | .csv
  data/interim/modulo_fiscal/modulo_fiscal_nao_correspondidos.csv
  data/manifests/dim_modulo_fiscal.json
"""
from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import (  # noqa: E402
    RAW_DIR, INTERIM_DIR, PROCESSED_DIR, CONFIG_DIR,
    cod_mun7, UF2IBGE, save_table, write_manifest,
)

CAMPOS = ["cod_municipio", "modulo_fiscal_ha", "fracao_minima_parcelamento_ha",
          "zona_tipica_modulo", "zona_pecuaria", "data_referencia", "fonte", "observacao"]


def _norm(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFKD", str(s)) if not unicodedata.combining(c))
    return s.strip().lower()


def _read_raw() -> pd.DataFrame:
    for name in ("modulo_fiscal_municipios.csv", "modulo_fiscal_municipios.xlsx",
                 "indices_basicos_incra.xlsx"):
        p = RAW_DIR / "incra" / name
        if p.exists():
            if p.suffix == ".csv":
                return pd.read_csv(p, sep=None, engine="python", dtype=str)
            return pd.read_excel(p, dtype=str)
    raise SystemExit("Bruto do INCRA ausente. Rode download/download_modulo_fiscal.py primeiro.")


def _find_col(cols, *keys):
    for c in cols:
        cl = _norm(c)
        if all(k in cl for k in keys):
            return c
    return None


def _read_dim() -> pd.DataFrame:
    p = PROCESSED_DIR / "dimensions" / "dim_municipio.parquet"
    if not p.exists():
        raise SystemExit("dim_municipio ausente. Rode process/process_geography.py primeiro.")
    return pd.read_parquet(p)[["cod_municipio", "nome_municipio", "uf"]]


def build() -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = _read_raw()
    dim = _read_dim()
    cols = list(raw.columns)

    c_cod = _find_col(cols, "cod") or _find_col(cols, "ibge")
    c_mf = _find_col(cols, "modulo", "fiscal") or _find_col(cols, "modulo")
    c_nome = _find_col(cols, "municipio") or _find_col(cols, "nome")
    c_uf = _find_col(cols, "uf") or _find_col(cols, "sigla")
    c_fmp = _find_col(cols, "fracao") or _find_col(cols, "fmp")

    def num(x):
        try:
            return float(str(x).replace(".", "").replace(",", "."))
        except (TypeError, ValueError):
            return None

    rows, nao_corresp = [], []
    dim_by_nomeuf = {(_norm(r.nome_municipio), r.uf): r.cod_municipio for r in dim.itertuples()}
    excec = {}
    ex_path = CONFIG_DIR / "modulo_fiscal_excecoes.csv"
    if ex_path.exists():
        ex = pd.read_csv(ex_path, sep=";", dtype=str)
        excec = {(_norm(r["nome"]), r["uf"]): cod_mun7(r["cod_municipio"]) for _, r in ex.iterrows()}

    for _, r in raw.iterrows():
        cod = cod_mun7(r[c_cod]) if c_cod else None
        uf = (str(r[c_uf]).strip().upper() if c_uf else (cod[:2] and None))
        if not cod and c_nome and c_uf:
            key = (_norm(r[c_nome]), uf)
            cod = dim_by_nomeuf.get(key) or excec.get(key)
        if not cod:
            nao_corresp.append({"nome": r.get(c_nome), "uf": r.get(c_uf) if c_uf else None,
                                "cod_bruto": r.get(c_cod) if c_cod else None})
            continue
        rows.append({
            "cod_municipio": cod,
            "modulo_fiscal_ha": num(r[c_mf]) if c_mf else None,
            "fracao_minima_parcelamento_ha": num(r[c_fmp]) if c_fmp else None,
            "zona_tipica_modulo": None,
            "zona_pecuaria": None,
            "data_referencia": None,
            "fonte": "INCRA — Índices Básicos (módulo fiscal)",
            "observacao": None,
        })
    df = pd.DataFrame(rows, columns=CAMPOS).drop_duplicates("cod_municipio")
    return df, pd.DataFrame(nao_corresp)


def main():
    df, nao = build()
    outs = save_table(df, PROCESSED_DIR / "dimensions" / "dim_modulo_fiscal")
    (INTERIM_DIR / "modulo_fiscal").mkdir(parents=True, exist_ok=True)
    nao_path = INTERIM_DIR / "modulo_fiscal" / "modulo_fiscal_nao_correspondidos.csv"
    nao.to_csv(nao_path, sep=";", index=False, encoding="utf-8")

    write_manifest("dim_modulo_fiscal", source="INCRA — módulo fiscal",
                   reference_date=None, source_files=[str(RAW_DIR / "incra")],
                   row_count=len(df), municipality_count=df["cod_municipio"].nunique(),
                   rejected_rows=len(nao), output_files=outs + [str(nao_path)],
                   warnings=[f"{len(nao)} registros sem correspondência (ver interim)"])
    print(f"[MÓDULO FISCAL] {len(df):,} municípios · {len(nao)} não correspondidos")


if __name__ == "__main__":
    main()
