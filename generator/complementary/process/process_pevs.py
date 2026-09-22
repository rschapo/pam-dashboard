"""
process_pevs.py — PEVS por município, produto e ano (Etapa 1, §6.8).

Consome o consolidado PEVS_municipios_completo.csv (copiado para data/raw/ibge/pevs/
por download_pevs.py) e produz a tabela longa `pevs_municipio`, mantendo
silvicultura e extração vegetal IDENTIFICADAS separadamente e aplicando os grupos
editáveis de config/forestry_groups.csv.

NÃO reimplementa o process_pevs.py do dashboard (que gera pevs.json). Aqui o alvo
é a base analítica complementar (parquet/csv), não o JSON do front-end.

Saída:
  data/processed/municipality/pevs_municipio.parquet | .csv
  data/manifests/pevs_municipio.json

Estrutura: cod_municipio, ano, tipo_atividade, produto, variavel, quantidade,
valor_producao_mil_reais, unidade_quantidade, grupo, fonte_tabela_sidra.
Descarta a categoria "Total" (soma sem sentido físico). Ausência = null.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import (  # noqa: E402
    RAW_DIR, PROCESSED_DIR, CONFIG_DIR, cod_mun7, clean_num, save_table, write_manifest,
)

TIPO_LABEL = {"Silvicultura": "Silvicultura", "Extracao": "Extração vegetal",
              "AreaSilvicultura": "Área plantada (silvicultura)"}
TIPO_TABELA = {"Silvicultura": 291, "Extracao": 289, "AreaSilvicultura": 5930}


def _read_pevs() -> pd.DataFrame:
    p = RAW_DIR / "ibge" / "pevs" / "PEVS_municipios_completo.csv"
    if not p.exists():
        raise SystemExit("PEVS consolidado ausente. Rode download/download_pevs.py primeiro.")
    return pd.read_csv(p, sep=";", encoding="utf-8-sig", dtype={"Cod_Municipio": str})


def _grupos() -> dict:
    g = pd.read_csv(CONFIG_DIR / "forestry_groups.csv", sep=";", dtype=str,
                    comment="#", keep_default_na=False)
    return {(r["tipo_atividade"], r["produto"].strip().lower()): r["grupo"] for _, r in g.iterrows()}


def build() -> pd.DataFrame:
    df = _read_pevs()
    df = df[df["Categoria"].astype(str).str.strip().str.lower() != "total"].copy()
    grupos = _grupos()

    rows = []
    for _, r in df.iterrows():
        tipo_raw = str(r.get("Tipo", ""))
        produto = str(r.get("Categoria", ""))
        grupo = grupos.get((tipo_raw, produto.strip().lower()))
        q = clean_num(r.get("q")) if "q" in df.columns else None
        v = clean_num(r.get("v")) if "v" in df.columns else None
        a = clean_num(r.get("a")) if "a" in df.columns else None
        rows.append({
            "cod_municipio": cod_mun7(r.get("Cod_Municipio")),
            "ano": int(r["Ano"]) if str(r.get("Ano", "")).isdigit() else None,
            "tipo_atividade": TIPO_LABEL.get(tipo_raw, tipo_raw),
            "produto": produto,
            "quantidade": q if tipo_raw != "AreaSilvicultura" else None,
            "area_ha": a if tipo_raw == "AreaSilvicultura" else None,
            "valor_producao_mil_reais": v,
            "unidade_quantidade": r.get("Unidade") or None,
            "grupo": grupo,
            "fonte_tabela_sidra": TIPO_TABELA.get(tipo_raw),
        })
    return pd.DataFrame(rows)


def main():
    df = build()
    outs = save_table(df, PROCESSED_DIR / "municipality" / "pevs_municipio")
    write_manifest("pevs_municipio", source="IBGE — PEVS (291/289/5930)",
                   reference_date=None, source_files=[str(RAW_DIR / 'ibge' / 'pevs' / 'PEVS_municipios_completo.csv')],
                   row_count=len(df), municipality_count=df["cod_municipio"].nunique(),
                   output_files=outs)
    print(f"[PEVS] {len(df):,} linhas · municípios={df['cod_municipio'].nunique():,} · "
          f"anos={df['ano'].min()}–{df['ano'].max()}")


if __name__ == "__main__":
    main()
