"""
enrich_geo.py
Consulta a API de localidades do IBGE e adiciona Microrregiao / Mesorregiao
a todos os CSVs municipais do PAM.
"""

import os
from pathlib import Path

import requests
import pandas as pd
import time

# Raiz dos brutos IBGE: PAM_RAW_DIR, data/raw_dir.txt ou data/raw (ibge_common)
from ibge_common import RAW_IBGE  # brutos fora do projeto: ver ibge_common._raiz_bruta
BASE = str(RAW_IBGE / "pam")
RAW  = str(RAW_IBGE / "pam" / "raw")

# ── 1. Baixar hierarquia geográfica do IBGE ──────────────────────────────────
print("Consultando API de localidades do IBGE...")
url = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
for tentativa in range(3):
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        localidades = r.json()
        break
    except Exception as e:
        print(f"  Tentativa {tentativa+1} falhou: {e}")
        time.sleep(5)
else:
    raise RuntimeError("Não foi possível acessar a API de localidades do IBGE.")

print(f"  {len(localidades)} municípios recebidos da API.")

# ── 2. Montar lookup: cod_municipio (7 dígitos str) → geo ────────────────────
lookup = {}
for loc in localidades:
    cod = str(loc["id"])                                      # 7 dígitos
    micro = loc.get("microrregiao") or {}
    meso  = micro.get("mesorregiao") or {}
    lookup[cod] = {
        "Cod_Microrregiao" : str(micro.get("id", "")),
        "Microrregiao"     : micro.get("nome", ""),
        "Cod_Mesorregiao"  : str(meso.get("id", "")),
        "Mesorregiao"      : meso.get("nome", ""),
    }

print(f"  Lookup montado: {len(lookup)} entradas.\n")

# ── 3. Função de enriquecimento ──────────────────────────────────────────────
def enriquecer(df):
    cod_col = "Cod_Municipio"
    df[cod_col] = df[cod_col].astype(str).str.zfill(7)

    geo_df = pd.DataFrame.from_dict(lookup, orient="index").reset_index()
    geo_df.rename(columns={"index": cod_col}, inplace=True)

    df = df.merge(geo_df, on=cod_col, how="left")

    cols = list(df.columns)
    geo_cols = ["Cod_Microrregiao", "Microrregiao", "Cod_Mesorregiao", "Mesorregiao"]
    for c in geo_cols:
        if c in cols:
            cols.remove(c)

    ref = "UF" if "UF" in cols else cols[0]
    idx = cols.index(ref) + 1
    for i, c in enumerate(geo_cols):
        cols.insert(idx + i, c)

    return df[cols]

# ── 4. Processar arquivos municipais ────────────────────────────────────────
arquivos = [
    "PAM_municipios_temporarias.csv",
    "PAM_municipios_permanentes.csv",
    "PAM_municipios_completo.csv",
]

for fname in arquivos:
    fpath = os.path.join(BASE, fname)
    if not os.path.exists(fpath):
        print(f"  [AVISO] Arquivo não encontrado: {fname}")
        continue

    print(f"Processando {fname}...")
    df = pd.read_csv(fpath, sep=";", dtype={"Cod_Municipio": str})

    df = enriquecer(df)

    nulos = df["Microrregiao"].isna().sum() + (df["Microrregiao"] == "").sum()
    cobertura = round((1 - nulos / len(df)) * 100, 1)

    df.to_csv(fpath, sep=";", index=False)
    size_mb = round(os.path.getsize(fpath) / 1_048_576, 1)
    print(f"  [SALVO] {fname} | {len(df):,} linhas | {size_mb} MB | cobertura geo: {cobertura}%")

# ── 5. Regenerar XLSX ─────────────────────────────────────────────────────────
print("\nRegenerando PAM_completo.xlsx...")
xlsx_path = os.path.join(BASE, "PAM_completo.xlsx")

sheets = {
    "Municipios_Completo" : "PAM_municipios_completo.csv",
    "Temporarias"         : "PAM_municipios_temporarias.csv",
    "Permanentes"         : "PAM_municipios_permanentes.csv",
    "Estados"             : "PAM_estados.csv",
    "Brasil"              : "PAM_brasil.csv",
    "Dicionario"          : "dicionario_dados.csv",
}

with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
    for sheet_name, csv_name in sheets.items():
        fpath = os.path.join(BASE, csv_name)
        if os.path.exists(fpath):
            df = pd.read_csv(fpath, sep=";")
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            print(f"  [ABA] {sheet_name} | {len(df):,} linhas")

size_mb = round(os.path.getsize(xlsx_path) / 1_048_576, 1)
print(f"\n[SALVO] PAM_completo.xlsx | {size_mb} MB")
print("\n=== ENRIQUECIMENTO CONCLUÍDO ===")
