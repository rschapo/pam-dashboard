"""
PPM Data Processor — Pesquisa da Pecuária Municipal 2004-2024
Reads the CSV produced by download_ppm_ibge.py and writes public/data/ppm.json.

Kept separate from pkg.json (which already carries ufs_info/mic_info/mun_info —
same UFs/microrregiões/municípios, no need to duplicate them here) so it can be
loaded lazily by the frontend only when a livestock view is opened.

Run from the project root, after generator/download_ppm_ibge.py has finished:
    py generator/process_ppm.py
"""

import sys, json, math
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
import requests

CSV     = r"C:\Users\schap\Downloads\IBGE\dados_ppm\PPM_municipios_completo.csv"
OUT_DIR = Path(__file__).parent.parent / "public" / "data"
OUT_PPM = OUT_DIR / "ppm.json"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# 1. LOAD CSV
# ─────────────────────────────────────────────────────────────────────────────
print("Loading CSV …")
df = pd.read_csv(CSV, sep=";", encoding="utf-8-sig", dtype={"Cod_Municipio": "str"})
print(f"  Raw rows: {len(df):,}")

# "Total" (tabela 74) soma litros + dúzias + kg num único número sem sentido físico — descarta.
df = df[df["Categoria"] != "Total"].copy()

anos = sorted(df["Ano"].dropna().unique().astype(int).tolist())
N_ANOS  = len(anos)
ano_idx = {a: i for i, a in enumerate(anos)}
print(f"  Anos: {anos[0]}–{anos[-1]} ({N_ANOS})")

rebanho_cats  = sorted(df.loc[df["Tipo"] == "Rebanho",  "Categoria"].unique().tolist())
producao_cats = sorted(df.loc[df["Tipo"] == "Producao", "Categoria"].unique().tolist())
print(f"  Rebanho: {len(rebanho_cats)} categorias  |  Produção: {len(producao_cats)} categorias")

# Normaliza as duas tabelas de origem num único par q(uantidade)/v(alor) por linha:
#   Rebanho  -> q = Efetivo_Cabecas (cabeças), sem valor monetário
#   Producao -> q = Quantidade,                v = Valor_mil_reais
df["_q"] = df.get("Efetivo_Cabecas")
if "Quantidade" in df.columns:
    df["_q"] = df["_q"].fillna(df["Quantidade"])
df["_v"] = df.get("Valor_mil_reais", 0)
df["_v"] = df["_v"].fillna(0) if df["_v"] is not None else 0

# ─────────────────────────────────────────────────────────────────────────────
# 2. Cod_Microrregiao — a PPM/SIDRA não devolve isso na consulta municipal;
#    busca o mapeamento município → microrregião na API de localidades do IBGE.
# ─────────────────────────────────────────────────────────────────────────────
print("Buscando mapeamento município → microrregião (API IBGE) …")
r = requests.get("https://servicodados.ibge.gov.br/api/v1/localidades/municipios", timeout=60)
r.raise_for_status()
MUN2MIC = {str(m["id"]): str(m["microrregiao"]["id"])
           for m in r.json() if m.get("microrregiao")}
df["Cod_Microrregiao"] = df["Cod_Municipio"].map(MUN2MIC)

sem_mic = int(df["Cod_Microrregiao"].isna().sum())
if sem_mic:
    print(f"  [AVISO] {sem_mic} linha(s) sem microrregião mapeada — descartadas")
    df = df[df["Cod_Microrregiao"].notna()].copy()

# ─────────────────────────────────────────────────────────────────────────────
# 3. Agregação — {chave: {categoria: {"q":[...], "v":[...]}}}
# ─────────────────────────────────────────────────────────────────────────────
def _empty():
    return {"q": [0] * N_ANOS, "v": [0] * N_ANOS}

def build_level(key_col):
    out = {}
    agg = df.groupby([key_col, "Categoria", "Ano"], as_index=False, sort=False).agg(
        q=("_q", "sum"), v=("_v", "sum"))
    for row in agg.itertuples(index=False):
        key = str(getattr(row, key_col))
        ai  = ano_idx.get(int(row.Ano))
        if ai is None: continue
        cat = row.Categoria
        if key not in out: out[key] = {}
        if cat not in out[key]: out[key][cat] = _empty()
        d = out[key][cat]
        d["q"][ai] = round(float(row.q or 0), 1)
        d["v"][ai] = round(float(row.v or 0), 1)
    return out

print("Building EST_DATA …")
EST_DATA = build_level("UF")
print(f"  Estados: {len(EST_DATA)}")

print("Building MIC_DATA …")
MIC_DATA = build_level("Cod_Microrregiao")
print(f"  Microrregiões: {len(MIC_DATA)}")

print("Building MUN_DATA …")
MUN_DATA = build_level("Cod_Municipio")
print(f"  Municípios: {len(MUN_DATA)}")

# ─────────────────────────────────────────────────────────────────────────────
# 4. Write output
# ─────────────────────────────────────────────────────────────────────────────
PPM = {
    "anos":                anos,
    "rebanho_categorias":  rebanho_cats,
    "producao_categorias": producao_cats,
    "est_data":            EST_DATA,
    "mic_data":            MIC_DATA,
    "mun_data":            MUN_DATA,
}

def _clean(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return 0
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj

print("Sanitizing NaN values …")
PPM = _clean(PPM)

print("Writing ppm.json …")
OUT_PPM.write_text(json.dumps(PPM, ensure_ascii=False, separators=(',', ':')), encoding="utf-8")
size = OUT_PPM.stat().st_size / 1_048_576
print(f"  ppm.json: {size:.1f} MB  ->  {OUT_PPM}")

print("\nDone!")
