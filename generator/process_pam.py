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
CROP_GROUPS_CSV = Path(__file__).parent / "crop_groups.csv"

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
    "urucum","erva-mate","carnauba","carnaúba"
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

anos = sorted(df["Ano"].dropna().unique().astype(int).tolist())
culturas = sorted(df["Cultura"].dropna().unique().tolist())
N_ANOS = len(anos)
ano_idx = {a: i for i, a in enumerate(anos)}
print(f"  Anos: {anos[0]}–{anos[-1]} ({N_ANOS})  |  Culturas: {len(culturas)}")

# ─────────────────────────────────────────────────────────────────────────────
# 1b. CROP GROUPS — maintainable table (generator/crop_groups.csv)
#
# tipo (TEM/PER) and COL (0/1, "Grãos/Colheitadeiras") live in this CSV so they
# can be edited without touching code. On first run (file missing) it is
# bootstrapped from the legacy keyword/fuzzy rules below, preserving today's
# classification as the starting point for future manual maintenance.
# ─────────────────────────────────────────────────────────────────────────────
def _bootstrap_group_table(culturas_all):
    perm_kw = [k.lower() for k in PERMANENTES_KEYWORDS]
    col_set_boot = set()
    for target in COLHEITADEIRAS_APPROX:
        tl = target.lower().replace("(","").replace(")","").strip()
        for c in culturas_all:
            cl = c.lower().replace("(","").replace(")","").strip()
            if tl == cl or tl in cl or cl in tl:
                col_set_boot.add(c)
                break
    rows = []
    for c in culturas_all:
        tipo = "PER" if any(k in c.lower() for k in perm_kw) else "TEM"
        rows.append({"cultura": c, "tipo": tipo, "COL": 1 if c in col_set_boot else 0})
    out = pd.DataFrame(rows).sort_values("cultura")
    out.to_csv(CROP_GROUPS_CSV, index=False, encoding="utf-8-sig")
    print(f"  crop_groups.csv criado com {len(out)} culturas (bootstrap) -> {CROP_GROUPS_CSV}")
    return out

if CROP_GROUPS_CSV.exists():
    print(f"Carregando agrupamentos de {CROP_GROUPS_CSV.name} ...")
    grp_df = pd.read_csv(CROP_GROUPS_CSV, encoding="utf-8-sig", dtype={"tipo": str})
else:
    print("crop_groups.csv não encontrado — gerando pela primeira vez ...")
    grp_df = _bootstrap_group_table(culturas)

GROUP_COLS = [c for c in grp_df.columns if c not in ("cultura","tipo")]
for g in GROUP_COLS:
    grp_df[g] = grp_df[g].fillna(0).astype(int)

known = set(grp_df["cultura"])
novas = [c for c in culturas if c not in known]
if novas:
    print(f"  [AVISO] {len(novas)} cultura(s) nova(s) sem entrada em crop_groups.csv "
          f"— adicionadas com default TEM/{'=0, '.join(GROUP_COLS)}=0, revise manualmente:")
    for c in novas:
        print(f"    - {c}")
    extra = pd.DataFrame([{"cultura": c, "tipo": "TEM", **{g: 0 for g in GROUP_COLS}} for c in novas])
    grp_df = pd.concat([grp_df, extra], ignore_index=True)
    grp_df.to_csv(CROP_GROUPS_CSV, index=False, encoding="utf-8-sig")

TIPO_MAP = dict(zip(grp_df["cultura"], grp_df["tipo"]))
df["_tipo"] = df["Cultura"].map(TIPO_MAP).fillna("TEM")

perm_culturas = sorted(df.loc[df["_tipo"]=="PER","Cultura"].unique().tolist())
temp_culturas = sorted(df.loc[df["_tipo"]=="TEM","Cultura"].unique().tolist())
print(f"  Permanentes: {len(perm_culturas)} | Temporárias: {len(temp_culturas)}")

col_set = set(grp_df.loc[grp_df["COL"]==1, "cultura"])
colheitadeiras = sorted([c for c in col_set if c in set(culturas)])

# "Tratores": temporárias que NÃO são colhidas por colheitadeira (regra automática,
# não é coluna do arquivo — culturas que dependem de trator p/ plantio/trato mas
# são colhidas manualmente ou por outro processo, ex: cana, mandioca, algodão).
tratores = sorted([c for c in temp_culturas if c not in col_set])
print(f"  Colheitadeiras: {len(colheitadeiras)}  |  Tratores: {len(tratores)}")

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
tra_set = set(tratores)

def _mic_grupo(c):
    if c in col_set: return "COL"
    if c in tra_set: return "TRA"
    return "PER"  # every cultura is TEM (COL or TRA) or PER — see partition above

df["_grupo"] = df["Cultura"].apply(_mic_grupo)

GROUP_MASKS = {
    "TEM": df["_tipo"] == "TEM",
    "PER": df["_tipo"] == "PER",
    "COL": df["_grupo"] == "COL",
    "TRA": df["_grupo"] == "TRA",
}

mic_all = df.groupby(["Cod_Microrregiao","Ano"], as_index=False, sort=False).agg(
    a=("Area_Colhida_ha","sum"), p=("Quantidade_Produzida_ton","sum"), v=("Valor_Producao_mil_reais","sum"))
mic_all["grupo"] = "ALL"

mic_group_tables = [mic_all]
for grp, mask in GROUP_MASKS.items():
    t = df[mask].groupby(["Cod_Microrregiao","Ano"], as_index=False, sort=False).agg(
        a=("Area_Colhida_ha","sum"), p=("Quantidade_Produzida_ton","sum"), v=("Valor_Producao_mil_reais","sum"))
    t["grupo"] = grp
    mic_group_tables.append(t)

mic_each = df[df["_grupo"]=="COL"].groupby(["Cod_Microrregiao","Cultura","Ano"], as_index=False, sort=False).agg(
    a=("Area_Colhida_ha","sum"), p=("Quantidade_Produzida_ton","sum"), v=("Valor_Producao_mil_reais","sum"))
mic_each = mic_each.rename(columns={"Cultura":"grupo"})
mic_group_tables.append(mic_each)

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

for tbl in mic_group_tables:
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
for grp, mask in GROUP_MASKS.items():
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
    "tratores":       tratores,
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
