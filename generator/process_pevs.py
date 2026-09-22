"""
PEVS Data Processor — Produção da Extração Vegetal e da Silvicultura.
Lê o CSV produzido por download_pevs_ibge.py e grava public/data/pevs.json.

Mantido separado do pkg.json (que já carrega ufs_info/mic_info/mun_info — mesmas
UFs/microrregiões/municípios, sem duplicar aqui) para ser carregado sob demanda
pelo frontend só quando a aba Silvicultura é aberta — exatamente como o ppm.json.

Estrutura do pevs.json (espelha o ppm.json, com "tipo" no lugar de rebanho/produção):
    {
      "anos": [2004, …],
      "tipos": ["Silvicultura", "Extração vegetal", "Área plantada"],
      "categorias_por_tipo": { "<tipo>": [categorias…] },
      "metricas_por_tipo":   { "Silvicultura": ["q","v"], "Área plantada": ["a"], … },
      "unidades":            { "<categoria>": "m³" | "t" | "ha" | … },
      "est_data" / "mic_data" / "mun_data":
            { "<chave>": { "<tipo>||<categoria>": {"q":[…],"v":[…],"a":[…]} } }
    }

Rodar a partir da raiz do projeto, depois de generator/download_pevs_ibge.py:
    py generator/process_pevs.py
"""

import sys, json, math
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
import requests

RAW_IBGE = Path(__file__).resolve().parent.parent / "data" / "raw" / "ibge"
CSV     = RAW_IBGE / "pevs" / "PEVS_municipios_completo.csv"
OUT_DIR = Path(__file__).parent.parent / "public" / "data"
OUT     = OUT_DIR / "pevs.json"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Rótulos amigáveis para o frontend (a coluna Tipo vem "crua" do coletor)
TIPO_LABEL = {
    "Silvicultura":     "Silvicultura",
    "Extracao":         "Extração vegetal",
    "AreaSilvicultura": "Área plantada",
}
# Métricas que cada tipo fornece
TIPO_METRICAS = {
    "Silvicultura":     ["q", "v"],
    "Extração vegetal": ["q", "v"],
    "Área plantada":    ["a"],
}
SEP = "||"  # separador da chave composta tipo||categoria

# ─────────────────────────────────────────────────────────────────────────────
# 1. LOAD CSV
# ─────────────────────────────────────────────────────────────────────────────
print("Loading CSV …")
df = pd.read_csv(CSV, sep=";", encoding="utf-8-sig", dtype={"Cod_Municipio": "str"})
print(f"  Raw rows: {len(df):,}")

# rótulo amigável do tipo
df["TipoLabel"] = df["Tipo"].map(TIPO_LABEL).fillna(df["Tipo"])

# descarta a categoria "Total" (soma sem sentido físico entre produtos de unidades diferentes)
df = df[df["Categoria"].astype(str).str.strip().str.lower() != "total"].copy()

# métricas presentes
for col in ("q", "v", "a"):
    if col not in df.columns:
        df[col] = 0.0
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

anos = sorted(df["Ano"].dropna().unique().astype(int).tolist())
N_ANOS  = len(anos)
ano_idx = {a: i for i, a in enumerate(anos)}
print(f"  Anos: {anos[0]}–{anos[-1]} ({N_ANOS})")

tipos = [t for t in ["Silvicultura", "Extração vegetal", "Área plantada"]
         if t in set(df["TipoLabel"])]

categorias_por_tipo, unidades = {}, {}
for t in tipos:
    cats = sorted(df.loc[df["TipoLabel"] == t, "Categoria"].dropna().unique().tolist())
    categorias_por_tipo[t] = cats
    for c in cats:
        u = df.loc[(df["TipoLabel"] == t) & (df["Categoria"] == c), "Unidade"].dropna()
        if len(u):
            unidades[c] = str(u.mode().iat[0]) if len(u.mode()) else str(u.iloc[0])
    print(f"  {t}: {len(cats)} categorias")

# chave composta tipo||categoria (nome sem "_" inicial p/ funcionar no itertuples)
df["catkey"] = df["TipoLabel"].astype(str) + SEP + df["Categoria"].astype(str)

# ─────────────────────────────────────────────────────────────────────────────
# 2. Cod_Microrregiao — a PEVS/SIDRA não devolve na consulta municipal;
#    busca o mapeamento município → microrregião na API de localidades do IBGE
#    (mesma abordagem do process_ppm.py).
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
# 3. Agregação — {chave_geo: {tipo||categoria: {"q":[…],"v":[…],"a":[…]}}}
# ─────────────────────────────────────────────────────────────────────────────
def _empty():
    return {"q": [0] * N_ANOS, "v": [0] * N_ANOS, "a": [0] * N_ANOS}

def build_level(key_col):
    out = {}
    agg = df.groupby([key_col, "catkey", "Ano"], as_index=False, sort=False).agg(
        q=("q", "sum"), v=("v", "sum"), a=("a", "sum"))
    for row in agg.itertuples(index=False):
        key = str(getattr(row, key_col))
        ai  = ano_idx.get(int(row.Ano))
        if ai is None: continue
        ck = row.catkey
        if key not in out: out[key] = {}
        if ck not in out[key]: out[key][ck] = _empty()
        d = out[key][ck]
        d["q"][ai] = round(float(row.q or 0), 1)
        d["v"][ai] = round(float(row.v or 0), 1)
        d["a"][ai] = round(float(row.a or 0), 1)
    return out

print("Building EST_DATA …");  EST_DATA = build_level("UF")
print(f"  Estados: {len(EST_DATA)}")
print("Building MIC_DATA …");  MIC_DATA = build_level("Cod_Microrregiao")
print(f"  Microrregiões: {len(MIC_DATA)}")
print("Building MUN_DATA …");  MUN_DATA = build_level("Cod_Municipio")
print(f"  Municípios: {len(MUN_DATA)}")

# ─────────────────────────────────────────────────────────────────────────────
# 4. Write output
# ─────────────────────────────────────────────────────────────────────────────
PEVS = {
    "anos":                anos,
    "tipos":               tipos,
    "categorias_por_tipo": categorias_por_tipo,
    "metricas_por_tipo":   {t: TIPO_METRICAS.get(t, ["q", "v"]) for t in tipos},
    "unidades":            unidades,
    "sep":                 SEP,
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
PEVS = _clean(PEVS)

print("Writing pevs.json …")
OUT.write_text(json.dumps(PEVS, ensure_ascii=False, separators=(',', ':')), encoding="utf-8")
size = OUT.stat().st_size / 1_048_576
print(f"  pevs.json: {size:.1f} MB  ->  {OUT}")

print("\nDone! (lembre-se de: git add -f public/data/pevs.json)")
