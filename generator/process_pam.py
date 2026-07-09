"""
PAM Data Processor — Produção Agrícola Municipal 2004-2024
Reads the IBGE PAM CSV and writes JSON files to public/data/.

Run from the project root:
    py generator/process_pam.py

Outputs:
    public/data/pkg.json      — all agricultural data (stats, meta)
    public/data/geo_uf.json   — UF polygon GeoJSON
    public/data/geo_mic.json  — Microregion polygon GeoJSON
"""

import sys, json, os, math
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Force UTF-8 output on Windows (avoids cp1252 crash on special chars)
sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
import requests

# ── Paths ────────────────────────────────────────────────────────────────────
CSV      = r"C:\Users\schap\Downloads\IBGE\dados_pam\PAM_municipios_completo.csv"
OUT_DIR  = Path(__file__).parent.parent / "public" / "data"
OUT_PKG  = OUT_DIR / "pkg.json"
OUT_GEO_UF  = OUT_DIR / "geo_uf.json"
OUT_GEO_MIC = OUT_DIR / "geo_mic.json"

OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── IBGE state code → 2-letter abbreviation ──────────────────────────────────
IBGE2UF = {
    "11":"RO","12":"AC","13":"AM","14":"RR","15":"PA","16":"AP","17":"TO",
    "21":"MA","22":"PI","23":"CE","24":"RN","25":"PB","26":"PE","27":"AL","28":"SE","29":"BA",
    "31":"MG","32":"ES","33":"RJ","35":"SP",
    "41":"PR","42":"SC","43":"RS","50":"MS","51":"MT","52":"GO","53":"DF"
}

UF_NAMES = {
    "RO":"Rondônia","AC":"Acre","AM":"Amazonas","RR":"Roraima","PA":"Pará","AP":"Amapá","TO":"Tocantins",
    "MA":"Maranhão","PI":"Piauí","CE":"Ceará","RN":"Rio Grande do Norte","PB":"Paraíba",
    "PE":"Pernambuco","AL":"Alagoas","SE":"Sergipe","BA":"Bahia",
    "MG":"Minas Gerais","ES":"Espírito Santo","RJ":"Rio de Janeiro","SP":"São Paulo",
    "PR":"Paraná","SC":"Santa Catarina","RS":"Rio Grande do Sul",
    "MS":"Mato Grosso do Sul","MT":"Mato Grosso","GO":"Goiás","DF":"Distrito Federal"
}

UF_REGION = {
    "RO":"N","AC":"N","AM":"N","RR":"N","PA":"N","AP":"N","TO":"N",
    "MA":"NE","PI":"NE","CE":"NE","RN":"NE","PB":"NE","PE":"NE","AL":"NE","SE":"NE","BA":"NE",
    "MG":"SE","ES":"SE","RJ":"SE","SP":"SE",
    "PR":"S","SC":"S","RS":"S",
    "MS":"CO","MT":"CO","GO":"CO","DF":"CO"
}

COLHEITADEIRAS_APPROX = [
    "Arroz (em casca)", "Aveia (em grão)", "Centeio (em grão)", "Cevada (em grão)",
    "Ervilha (em grão)", "Fava (em grão)", "Feijão (em grão)", "Girassol (em grão)",
    "Linho (semente)", "Milho (em grão)", "Soja (em grão)", "Sorgo (em grão)",
    "Trigo (em grão)", "Triticale (em grão)"
]

PERMANENTES_KEYWORDS = [
    "banana","café","cacao","cacau","laranja","tangerina","lima","limão","limao",
    "uva","coco","maçã","maca","pêssego","pessego","manga","goiaba","abacate",
    "guaraná","guarana","dendê","dende","palma","pimenta-do-reino","maracujá","maracuja",
    "figo","caju","acerola","graviola","pitanga","açaí","acai","cupuaçu","cupuacu",
    "borracha","seringueira","sisal","abacaxi","mamão","mamao",
    "noz-pecã","pecan","macadamia","macadâmia","castanha-do-para","castanha do pará",
    "urucum","erva-mate","mate","carnauba","carnaúba"
]

# ─────────────────────────────────────────────────────────────────────────────
# 1. LOAD CSV
# ─────────────────────────────────────────────────────────────────────────────
print("Loading CSV …")
df = pd.read_csv(CSV, sep=";",
    dtype={"Cod_Municipio":"str","Cod_Microrregiao":"str","Cod_Mesorregiao":"str"})

print(f"  Raw rows: {len(df):,}   {df['UF'].nunique() if 'UF' in df.columns else '?'} states in CSV")

df["UF"] = df["Cod_Municipio"].str[:2].map(IBGE2UF)
df = df[df["UF"].notna()].copy()
print(f"  After UF fix: {len(df):,} rows, {df['UF'].nunique()} states")

MUN_COL = None
for candidate in ["Municipio","Nome_Municipio","municipio","nome_municipio","MUNICIPIO"]:
    if candidate in df.columns:
        MUN_COL = candidate
        break
if MUN_COL is None:
    df["_Municipio"] = df["Cod_Municipio"]
    MUN_COL = "_Municipio"
print(f"  Municipality column: {MUN_COL}")

TIPO_COL = None
for candidate in ["Tipo_Lavoura","tipo_lavoura","Tipo","tipo","Tabela","tabela"]:
    if candidate in df.columns:
        TIPO_COL = candidate
        break

if TIPO_COL:
    tipo_map = {}
    for v in df[TIPO_COL].dropna().unique():
        vs = str(v).lower()
        tipo_map[v] = "PER" if ("perm" in vs or "1613" in vs) else "TEM"
    df["_tipo"] = df[TIPO_COL].map(tipo_map).fillna("TEM")
else:
    perm_kw = [k.lower() for k in PERMANENTES_KEYWORDS]
    df["_tipo"] = df["Cultura"].apply(
        lambda c: "PER" if any(k in str(c).lower() for k in perm_kw) else "TEM")

perm_culturas = sorted(df.loc[df["_tipo"]=="PER","Cultura"].unique().tolist())
temp_culturas = sorted(df.loc[df["_tipo"]=="TEM","Cultura"].unique().tolist())
print(f"  Permanentes: {len(perm_culturas)} | Temporárias: {len(temp_culturas)}")

anos = sorted(df["Ano"].dropna().unique().astype(int).tolist())
culturas = sorted(df["Cultura"].dropna().unique().tolist())
N_ANOS = len(anos)
ano_idx = {a: i for i, a in enumerate(anos)}
print(f"  Anos: {anos[0]}–{anos[-1]} ({N_ANOS})  |  Culturas: {len(culturas)}")

col_set = set()
for target in COLHEITADEIRAS_APPROX:
    tl = target.lower().replace("(","").replace(")","").strip()
    for c in culturas:
        cl = c.lower().replace("(","").replace(")","").strip()
        if tl == cl or tl in cl or cl in tl:
            col_set.add(c)
            break
    else:
        col_set.add(target)
colheitadeiras = sorted([c for c in col_set if c in set(culturas)])
print(f"  Colheitadeiras matched: {len(colheitadeiras)}")

# ─────────────────────────────────────────────────────────────────────────────
# 2. EST_DATA
# ─────────────────────────────────────────────────────────────────────────────
print("Building EST_DATA …")
est_agg = df.groupby(["UF","Cultura","Ano"], as_index=False, sort=False).agg(
    a=("Area_Colhida_ha","sum"),
    p=("Quantidade_Produzida_ton","sum"),
    v=("Valor_Producao_mil_reais","sum"),
    r=("Rendimento_Medio_kg_ha","mean")
)
EST_DATA = {}
for row in est_agg.itertuples(index=False):
    uf, c, ano = row.UF, row.Cultura, int(row.Ano)
    ai = ano_idx.get(ano)
    if ai is None: continue
    if uf not in EST_DATA: EST_DATA[uf] = {}
    if c not in EST_DATA[uf]:
        EST_DATA[uf][c] = {"a":[0]*N_ANOS,"p":[0]*N_ANOS,"v":[0]*N_ANOS,"r":[0]*N_ANOS}
    d = EST_DATA[uf][c]
    d["a"][ai] = round(float(row.a or 0),1)
    d["p"][ai] = round(float(row.p or 0),1)
    d["v"][ai] = round(float(row.v or 0),1)
    d["r"][ai] = round(float(row.r or 0),2)
print(f"  States in EST_DATA: {len(EST_DATA)}")

# ─────────────────────────────────────────────────────────────────────────────
# 3. MIC_DATA
# ─────────────────────────────────────────────────────────────────────────────
print("Building MIC_DATA …")
perm_set = set(perm_culturas)

def _mic_grupo(c):
    if c in col_set: return "COL"
    if c in perm_set: return "PER"
    return "TEM"

df["_grupo"] = df["Cultura"].apply(_mic_grupo)

mic_all = df.groupby(["Cod_Microrregiao","Ano"], as_index=False, sort=False).agg(
    a=("Area_Colhida_ha","sum"), p=("Quantidade_Produzida_ton","sum"), v=("Valor_Producao_mil_reais","sum"))
mic_all["grupo"] = "ALL"

mic_tem = df[df["_tipo"]=="TEM"].groupby(["Cod_Microrregiao","Ano"], as_index=False, sort=False).agg(
    a=("Area_Colhida_ha","sum"), p=("Quantidade_Produzida_ton","sum"), v=("Valor_Producao_mil_reais","sum"))
mic_tem["grupo"] = "TEM"

mic_per = df[df["_tipo"]=="PER"].groupby(["Cod_Microrregiao","Ano"], as_index=False, sort=False).agg(
    a=("Area_Colhida_ha","sum"), p=("Quantidade_Produzida_ton","sum"), v=("Valor_Producao_mil_reais","sum"))
mic_per["grupo"] = "PER"

mic_col = df[df["_grupo"]=="COL"].groupby(["Cod_Microrregiao","Ano"], as_index=False, sort=False).agg(
    a=("Area_Colhida_ha","sum"), p=("Quantidade_Produzida_ton","sum"), v=("Valor_Producao_mil_reais","sum"))
mic_col["grupo"] = "COL"

mic_each = df[df["_grupo"]=="COL"].groupby(["Cod_Microrregiao","Cultura","Ano"], as_index=False, sort=False).agg(
    a=("Area_Colhida_ha","sum"), p=("Quantidade_Produzida_ton","sum"), v=("Valor_Producao_mil_reais","sum"))
mic_each = mic_each.rename(columns={"Cultura":"grupo"})

MIC_DATA = {}

def _fill_mic(sub):
    for row in sub.itertuples(index=False):
        mid = str(getattr(row,"Cod_Microrregiao"))
        ai  = ano_idx.get(int(row.Ano))
        if ai is None: continue
        g   = str(row.grupo)
        if mid not in MIC_DATA: MIC_DATA[mid] = {}
        if g not in MIC_DATA[mid]:
            MIC_DATA[mid][g] = {"a":[0]*N_ANOS,"p":[0]*N_ANOS,"v":[0]*N_ANOS}
        d = MIC_DATA[mid][g]
        d["a"][ai] = round(float(row.a or 0),1)
        d["p"][ai] = round(float(row.p or 0),1)
        d["v"][ai] = round(float(row.v or 0),1)

for tbl in [mic_all, mic_tem, mic_per, mic_col, mic_each]:
    _fill_mic(tbl)
print(f"  Microregiões in MIC_DATA: {len(MIC_DATA)}")

# ─────────────────────────────────────────────────────────────────────────────
# 4. MUN_DATA
# ─────────────────────────────────────────────────────────────────────────────
print("Building MUN_DATA …")
mun_agg = df.groupby(["Cod_Municipio","Ano"], as_index=False, sort=False).agg(
    a=("Area_Colhida_ha","sum"),
    p=("Quantidade_Produzida_ton","sum"),
    v=("Valor_Producao_mil_reais","sum")
)
MUN_DATA = {}
for row in mun_agg.itertuples(index=False):
    mid = str(row.Cod_Municipio)
    ai  = ano_idx.get(int(row.Ano))
    if ai is None: continue
    if mid not in MUN_DATA:
        MUN_DATA[mid] = {"a":[0]*N_ANOS,"p":[0]*N_ANOS,"v":[0]*N_ANOS}
    MUN_DATA[mid]["a"][ai] = round(float(row.a or 0),1)
    MUN_DATA[mid]["p"][ai] = round(float(row.p or 0),1)
    MUN_DATA[mid]["v"][ai] = round(float(row.v or 0),1)
print(f"  Municípios in MUN_DATA: {len(MUN_DATA)}")

# 4b. MUN_GRP_DATA
print("Building MUN_GRP_DATA …")
MUN_GRP_DATA = {}
for grp, mask in [
    ("TEM", df["_tipo"] == "TEM"),
    ("PER", df["_tipo"] == "PER"),
    ("COL", df["_grupo"] == "COL"),
]:
    sub = df[mask]
    gagg = sub.groupby(["Cod_Municipio","Ano"], as_index=False, sort=False).agg(
        a=("Area_Colhida_ha","sum"),
        p=("Quantidade_Produzida_ton","sum"),
        v=("Valor_Producao_mil_reais","sum")
    )
    gd = {}
    for row in gagg.itertuples(index=False):
        mid = str(row.Cod_Municipio)
        ai  = ano_idx.get(int(row.Ano))
        if ai is None: continue
        if mid not in gd:
            gd[mid] = {"a":[0]*N_ANOS,"p":[0]*N_ANOS,"v":[0]*N_ANOS}
        gd[mid]["a"][ai] = round(float(row.a or 0),1)
        gd[mid]["p"][ai] = round(float(row.p or 0),1)
        gd[mid]["v"][ai] = round(float(row.v or 0),1)
    MUN_GRP_DATA[grp] = gd
    print(f"  {grp}: {len(gd)} municipalities")

# ─────────────────────────────────────────────────────────────────────────────
# 5. INFO DICTS
# ─────────────────────────────────────────────────────────────────────────────
mic_info_df = df[["Cod_Microrregiao","Microrregiao","UF","Mesorregiao"]].drop_duplicates()
MIC_INFO = {}
for _, row in mic_info_df.iterrows():
    MIC_INFO[str(row["Cod_Microrregiao"])] = {
        "n": str(row["Microrregiao"]), "uf": str(row["UF"]), "ms": str(row["Mesorregiao"])
    }

UFS_INFO = {uf: {"n": UF_NAMES.get(uf, uf), "r": UF_REGION.get(uf,"")}
            for uf in sorted(df["UF"].unique())}

mun_info_df = df[[MUN_COL,"Cod_Municipio","UF","Cod_Microrregiao"]].drop_duplicates("Cod_Municipio")
MUN_INFO = {}
for _, row in mun_info_df.iterrows():
    MUN_INFO[str(row["Cod_Municipio"])] = {
        "n": str(row[MUN_COL]),
        "uf": str(row["UF"]),
        "mid": str(row["Cod_Microrregiao"])
    }
print(f"  States: {len(UFS_INFO)}  |  Micros: {len(MIC_INFO)}  |  Municípios: {len(MUN_INFO)}")

# ─────────────────────────────────────────────────────────────────────────────
# 6. GeoJSON
# ─────────────────────────────────────────────────────────────────────────────
BASE = "https://servicodados.ibge.gov.br/api/v3/malhas"

def fetch_uf_geo():
    url = f"{BASE}/paises/BR?formato=application/vnd.geo+json&qualidade=intermediaria&intrarregiao=UF"
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    geo = r.json()
    for f in geo.get("features", []):
        props = f.setdefault("properties", {})
        ca = props.get("codarea", "")
        code = str(int(ca)).zfill(2) if ca else ""
        props["uf"] = IBGE2UF.get(code, code)
    print(f"  UF features fetched: {len(geo.get('features', []))}")
    return geo

def fetch_mic_geo():
    url = f"{BASE}/paises/BR?formato=application/vnd.geo+json&qualidade=intermediaria&intrarregiao=microrregiao"
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    geo = r.json()
    for f in geo["features"]:
        props = f["properties"]
        ca = props.get("codarea", "")
        try:
            props["mid"] = str(int(ca))
        except (ValueError, TypeError):
            props["mid"] = str(ca)
    return geo

print("Downloading GeoJSON (parallel) …")
GEO_UF = GEO_MIC = None
with ThreadPoolExecutor(max_workers=2) as ex:
    fut_uf  = ex.submit(fetch_uf_geo)
    fut_mic = ex.submit(fetch_mic_geo)
    GEO_UF  = fut_uf.result()
    GEO_MIC = fut_mic.result()
print(f"  UF features: {len(GEO_UF['features'])}  |  Micro features: {len(GEO_MIC['features'])}")

# ─────────────────────────────────────────────────────────────────────────────
# 7. Write JSON files
# ─────────────────────────────────────────────────────────────────────────────
PKG = {
    "anos":           anos,
    "culturas":       culturas,
    "colheitadeiras": colheitadeiras,
    "permanentes":    perm_culturas,
    "temporarias":    temp_culturas,
    "ufs_info":       UFS_INFO,
    "mic_info":       MIC_INFO,
    "mun_info":       MUN_INFO,
    "est_data":       EST_DATA,
    "mic_data":       MIC_DATA,
    "mun_data":       MUN_DATA,
    "mun_grp_data":   MUN_GRP_DATA,
}

# ── Sanitize NaN / Inf before JSON serialisation ──────────────────────────────
# Python's json module writes float('nan') as bare NaN which is not valid JSON.
# Replace NaN and Inf with 0 so the browser can parse the file.
def _clean(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return 0
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj

print("Sanitizing NaN values …")
PKG = _clean(PKG)

print("Writing JSON files …")
OUT_PKG.write_text(json.dumps(PKG, ensure_ascii=False, separators=(',',':')), encoding="utf-8")
size = OUT_PKG.stat().st_size / 1_048_576
print(f"  pkg.json: {size:.1f} MB  ->  {OUT_PKG}")

OUT_GEO_UF.write_text(json.dumps(GEO_UF, ensure_ascii=False, separators=(',',':')), encoding="utf-8")
size = OUT_GEO_UF.stat().st_size / 1_048_576
print(f"  geo_uf.json: {size:.1f} MB  ->  {OUT_GEO_UF}")

OUT_GEO_MIC.write_text(json.dumps(GEO_MIC, ensure_ascii=False, separators=(',',':')), encoding="utf-8")
size = OUT_GEO_MIC.stat().st_size / 1_048_576
print(f"  geo_mic.json: {size:.1f} MB  ->  {OUT_GEO_MIC}")

print("\nDone! Deploy the public/ folder to Netlify.")
