"""
process_censo_agro.py — Censo Agropecuário 2017 em tabelas temáticas (Etapa 1, §6.3–6.4).

Lê os brutos por tema em data/raw/censo_agro/<tema>/ (gerados por download_censo_agro.py)
e grava uma tabela por tema, evitando uma única tabela larga:

  censo_agro_area_groups, censo_agro_family_farming, censo_agro_machinery,
  censo_agro_storage, censo_agro_irrigation, censo_agro_finance,
  censo_agro_technical_assistance, censo_agro_land_use, censo_agro_activity

Cada tabela: cod_municipio, ano_referencia, categoria, subcategoria, variavel,
valor, unidade, fonte_tabela_sidra. Ausência = null (nunca zero).

Harmonização de faixas de área (§6.4): usa config/area_groups.csv. Mantém a
classe original E gera as faixas harmonizadas, somando SÓ classes compatíveis e
marcando quando uma faixa não pôde ser reconstruída.

Também gera censo_agro_municipio_summary (resumo municipal enxuto).

Saídas em data/processed/municipality/ + manifests.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import (  # noqa: E402
    RAW_DIR, PROCESSED_DIR, CONFIG_DIR, cod_mun7, save_table, write_manifest,
)

TEMAS = ["area_groups", "family_farming", "land_condition", "machinery", "irrigation",
         "storage", "finance", "technical_assistance", "land_use", "activity"]
ANO = 2017
COLS = ["cod_municipio", "ano_referencia", "categoria", "subcategoria",
        "variavel", "valor", "unidade", "fonte_tabela_sidra"]


def _read_tema(tema: str) -> pd.DataFrame:
    d = RAW_DIR / "censo_agro" / tema
    if not d.exists():
        return pd.DataFrame(columns=COLS)
    frames = []
    for p in d.glob("*.csv"):
        try:
            df = pd.read_csv(p, sep=";", dtype={"cod_municipio": str})
            if not df.empty:
                frames.append(df)
        except Exception:
            pass
    if not frames:
        return pd.DataFrame(columns=COLS)
    df = pd.concat(frames, ignore_index=True)
    df["cod_municipio"] = df["cod_municipio"].map(cod_mun7)
    for c in COLS:
        if c not in df.columns:
            df[c] = None
    return df[COLS]


def harmonizar_area_groups(area_df: pd.DataFrame) -> pd.DataFrame:
    """Soma classes originais nas faixas harmonizadas, marcando incompatíveis."""
    if area_df.empty:
        return pd.DataFrame()
    mapa = pd.read_csv(CONFIG_DIR / "area_groups.csv", sep=";", dtype=str)
    m = {r["classe_original"].strip().lower(): (r["faixa_harmonizada"], r["compativel"])
         for _, r in mapa.iterrows()}
    df = area_df.copy()
    df["faixa_harmonizada"] = df["subcategoria"].astype(str).str.strip().str.lower().map(
        lambda s: m.get(s, (None, "0"))[0])
    df["compativel"] = df["subcategoria"].astype(str).str.strip().str.lower().map(
        lambda s: m.get(s, (None, "0"))[1])
    # mantém a original; agrega harmonizado apenas onde compativel==1
    comp = df[df["compativel"] == "1"].copy()
    comp["valor"] = pd.to_numeric(comp["valor"], errors="coerce")
    harm = (comp.groupby(["cod_municipio", "variavel", "faixa_harmonizada"], as_index=False)
                .agg(valor=("valor", "sum")))
    harm["ano_referencia"] = ANO
    harm["classificacao"] = "harmonizada"
    return harm


def _summary(temas_data: dict) -> pd.DataFrame:
    """Resumo municipal enxuto: nº estabelecimentos e área total (quando disponíveis)."""
    ag = temas_data.get("area_groups")
    if ag is None or ag.empty:
        return pd.DataFrame(columns=["cod_municipio", "ano_referencia"])
    a = ag.copy()
    a["valor"] = pd.to_numeric(a["valor"], errors="coerce")
    est = (a[a["variavel"].str.contains("estabeleciment", case=False, na=False)]
           .groupby("cod_municipio")["valor"].sum().rename("numero_estabelecimentos"))
    area = (a[a["variavel"].str.contains("área|area", case=False, na=False)]
            .groupby("cod_municipio")["valor"].sum().rename("area_estabelecimentos_ha"))
    out = pd.concat([est, area], axis=1).reset_index()
    out["ano_referencia"] = ANO
    return out


def main():
    temas_data, outs, total = {}, [], 0
    for tema in TEMAS:
        df = _read_tema(tema)
        temas_data[tema] = df
        if df.empty:
            continue
        outs += save_table(df, PROCESSED_DIR / "municipality" / f"censo_agro_{tema}")
        total += len(df)
        print(f"  censo_agro_{tema}: {len(df):,} linhas")

    if total == 0:
        print("[CENSO AGRO] Nenhum bruto encontrado em data/raw/censo_agro/<tema>/. "
              "Rode download/download_censo_agro.py (na sua máquina).")
        return

    harm = harmonizar_area_groups(temas_data.get("area_groups", pd.DataFrame()))
    if not harm.empty:
        outs += save_table(harm, PROCESSED_DIR / "municipality" / "censo_agro_area_groups_harmonizado")

    summ = _summary(temas_data)
    if not summ.empty:
        outs += save_table(summ, PROCESSED_DIR / "municipality" / "censo_agro_municipio_summary")

    write_manifest("censo_agro", source="IBGE — Censo Agropecuário 2017",
                   reference_date=f"{ANO}-12-31", source_files=[str(RAW_DIR / "censo_agro")],
                   row_count=total, output_files=outs)
    print(f"[CENSO AGRO] {total:,} linhas em {sum(1 for t in temas_data.values() if not t.empty)} temas")


if __name__ == "__main__":
    main()
