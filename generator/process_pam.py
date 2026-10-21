"""
PAM Data Processor — Produção Agrícola Municipal 2004-2024
Reads the IBGE PAM CSV and writes JSON files to public/data/.

Run from the project root:
    py generator/process_pam.py              (baixa as malhas de UF e microrregião de novo)
    py generator/process_pam.py --sem-malha  (só os dados; mantém geo_uf.json e geo_mic.json)

Outputs:
    public/data/pkg.json      — all agricultural data (stats, meta)
    public/data/pam_mun/*.json — uma cultura por arquivo, por município e ano, lido pelo
                                 front só quando a cultura é escolhida
    public/data/geo_uf.json   — UF polygon GeoJSON
    public/data/geo_mic.json  — Microregion polygon GeoJSON

Café: a PAM publica "Café (em grão) Total" e, desde 2012, as partes Arábica e
Canephora. As partes (coluna `pai` do crop_groups.csv) ficam selecionáveis uma a uma,
mas não entram em nenhum agregado (Todas, Permanentes, municípios, microrregiões):
somadas ao Total, contavam o café duas vezes (1,94 Mha a mais em 2025).
"""

import sys, json, os, math, re, unicodedata
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Force UTF-8 output on Windows (avoids cp1252 crash on special chars)
sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
import requests

from ibge_common import IBGE2UF, build_ufs_info, build_mic_info, build_mun_info, completar_microrregiao

# ── Paths ────────────────────────────────────────────────────────────────────
from ibge_common import RAW_IBGE  # brutos fora do projeto: ver ibge_common._raiz_bruta
CSV      = RAW_IBGE / "pam" / "PAM_municipios_completo.csv"
OUT_DIR  = Path(__file__).parent.parent / "public" / "data"
OUT_PKG  = OUT_DIR / "pkg.json"
OUT_GEO_UF  = OUT_DIR / "geo_uf.json"
OUT_GEO_MIC = OUT_DIR / "geo_mic.json"
OUT_MUN_CULT = OUT_DIR / "pam_mun"
CROP_GROUPS_CSV = Path(__file__).parent / "crop_groups.csv"
SEM_MALHA = "--sem-malha" in sys.argv

OUT_DIR.mkdir(parents=True, exist_ok=True)

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

# Município instalado depois de 2017 vem sem microrregião; sem isto ele formava uma
# microrregião "nan" à parte, e a de origem ficava sem a produção dele.
df = completar_microrregiao(df)
sem_mic = df["Cod_Microrregiao"].isna() | (df["Cod_Microrregiao"].astype(str) == "nan")
if sem_mic.any():
    print(f"  [AVISO] sem microrregião: {', '.join(sorted(df.loc[sem_mic, 'Cod_Municipio'].unique()))} "
          "— inclua em ibge_common.MICRO_MUNICIPIOS_NOVOS")

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

if "pai" not in grp_df.columns:
    grp_df["pai"] = ""
grp_df["pai"] = grp_df["pai"].fillna("").astype(str).str.strip()
GROUP_COLS = [c for c in grp_df.columns if c not in ("cultura","tipo","pai")]
for g in GROUP_COLS:
    grp_df[g] = grp_df[g].fillna(0).astype(int)

known = set(grp_df["cultura"])
novas = [c for c in culturas if c not in known]
if novas:
    # Tipo_Lavoura in the source CSV already reflects IBGE's own PAM table split
    # (1612=Temporaria, 1613=Permanente) per crop — use it instead of a blind
    # TEM default, which previously misclassified perennials like Acerola/
    # Cupuaçu/Graviola as temporárias.
    tipo_lavoura_map = df.drop_duplicates("Cultura").set_index("Cultura")["Tipo_Lavoura"]
    print(f"  [AVISO] {len(novas)} cultura(s) nova(s) sem entrada em crop_groups.csv "
          f"— adicionadas com tipo herdado de Tipo_Lavoura (fonte IBGE) e {'=0, '.join(GROUP_COLS)}=0, revise manualmente:")
    for c in novas:
        print(f"    - {c}")
    extra = pd.DataFrame([
        {"cultura": c,
         "tipo": "PER" if str(tipo_lavoura_map.get(c, "Temporaria")).startswith("Perm") else "TEM",
         **{g: 0 for g in GROUP_COLS}, "pai": ""}
        for c in novas
    ])
    grp_df = pd.concat([grp_df, extra], ignore_index=True)
    grp_df.to_csv(CROP_GROUPS_CSV, index=False, encoding="utf-8-sig")

TIPO_MAP = dict(zip(grp_df["cultura"], grp_df["tipo"]))
df["_tipo"] = df["Cultura"].map(TIPO_MAP).fillna("TEM")

# Partes de uma cultura que a PAM também publica no total (café Arábica e Canephora,
# dentro do Café Total): ficam fora de todo agregado. Um pai que não existe na PAM
# deixaria a parte sem total nenhum, e uma parte em grupo de máquina contaria duas vezes.
FILHAS = {c: p for c, p in zip(grp_df["cultura"], grp_df["pai"]) if p}
for filha, pai in FILHAS.items():
    if pai not in set(grp_df["cultura"]):
        sys.exit(f"[ERRO] crop_groups.csv: o pai '{pai}' de '{filha}' não é cultura da tabela")
    if filha in set(grp_df.loc[grp_df["COL"] == 1, "cultura"]):
        sys.exit(f"[ERRO] crop_groups.csv: '{filha}' é parte de '{pai}' e não pode estar em COL")
filha_mask = df["Cultura"].isin(FILHAS)
if FILHAS:
    print(f"  Partes fora dos agregados: {', '.join(FILHAS)} "
          f"({df.loc[filha_mask, 'Area_Colhida_ha'].sum():,.0f} ha somados na série)")

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
)
# Media simples entre municipios faria um de 5 ha pesar como um de 500 mil.
est_agg["r"] = (est_agg["p"] / est_agg["a"] * 1000).where(est_agg["a"] > 0, 0)
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

# Daqui em diante, todo agregado (micro, município, grupo) sai sem as partes do café.
dfa = df[~filha_mask]

GROUP_MASKS = {
    "TEM": dfa["_tipo"] == "TEM",
    "PER": dfa["_tipo"] == "PER",
    "COL": dfa["_grupo"] == "COL",
    "TRA": dfa["_grupo"] == "TRA",
}

mic_all = dfa.groupby(["Cod_Microrregiao","Ano"], as_index=False, sort=False).agg(
    a=("Area_Colhida_ha","sum"), p=("Quantidade_Produzida_ton","sum"), v=("Valor_Producao_mil_reais","sum"))
mic_all["grupo"] = "ALL"

mic_group_tables = [mic_all]
for grp, mask in GROUP_MASKS.items():
    t = dfa[mask].groupby(["Cod_Microrregiao","Ano"], as_index=False, sort=False).agg(
        a=("Area_Colhida_ha","sum"), p=("Quantidade_Produzida_ton","sum"), v=("Valor_Producao_mil_reais","sum"))
    t["grupo"] = grp
    mic_group_tables.append(t)

mic_each = dfa[dfa["_grupo"]=="COL"].groupby(["Cod_Microrregiao","Cultura","Ano"], as_index=False, sort=False).agg(
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
mun_agg = dfa.groupby(["Cod_Municipio","Ano"], as_index=False, sort=False).agg(
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
    sub = dfa[mask]
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

# 4c. Uma cultura por arquivo (public/data/pam_mun/<slug>.json)
# O pkg.json só tem o município pelo total e pelos grupos: escolhida uma cultura, o
# mapa de municípios mostrava o total do grupo. O front baixa o arquivo da cultura
# quando ela é escolhida. Formato: {cod: [[área...], [produção...], [valor...]]}, uma
# posição por ano de `anos`; null onde a PAM tem a linha sem o número (ausente,
# não zero), 0 onde o município não tem a cultura naquele ano.
def _slug(c):
    s = unicodedata.normalize("NFKD", c).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")

def _num(x):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return None
    x = round(float(x), 1)
    return int(x) if x.is_integer() else x

print("Building per-crop municipal files …")
ARQ_CULTURA = {c: _slug(c) for c in culturas}
if len(set(ARQ_CULTURA.values())) != len(ARQ_CULTURA):
    sys.exit("[ERRO] duas culturas dão o mesmo nome de arquivo em pam_mun/")
OUT_MUN_CULT.mkdir(parents=True, exist_ok=True)
for velho in OUT_MUN_CULT.glob("*.json"):
    velho.unlink()                  # cultura que saiu da PAM não deixa arquivo esquecido
# min_count=1: a linha sem número continua sem número (NaN → null), não vira zero
cult_mun = (df.groupby(["Cultura", "Cod_Municipio", "Ano"], sort=False)
              [["Area_Colhida_ha", "Quantidade_Produzida_ton", "Valor_Producao_mil_reais"]]
              .sum(min_count=1).reset_index()
              .rename(columns={"Area_Colhida_ha": "a", "Quantidade_Produzida_ton": "p",
                               "Valor_Producao_mil_reais": "v"}))
maior = (0, "")
for c, sub in cult_mun.groupby("Cultura", sort=False):
    mun = {}
    for row in sub.itertuples(index=False):
        ai = ano_idx.get(int(row.Ano))
        if ai is None: continue
        reg = mun.setdefault(str(row.Cod_Municipio), [[0] * N_ANOS, [0] * N_ANOS, [0] * N_ANOS])
        reg[0][ai], reg[1][ai], reg[2][ai] = _num(row.a), _num(row.p), _num(row.v)
    out = OUT_MUN_CULT / f"{ARQ_CULTURA[c]}.json"
    out.write_text(json.dumps({"cultura": c, "anos": anos, "mun": mun}, ensure_ascii=False,
                              separators=(",", ":"), allow_nan=False), encoding="utf-8")
    maior = max(maior, (out.stat().st_size, out.name))
print(f"  {len(ARQ_CULTURA)} arquivos em {OUT_MUN_CULT.name}/ · maior: {maior[1]} ({maior[0] / 1_048_576:.2f} MB)")

# ─────────────────────────────────────────────────────────────────────────────
# 5. INFO DICTS
# ─────────────────────────────────────────────────────────────────────────────
MIC_INFO = build_mic_info(df)
UFS_INFO = build_ufs_info(df)
MUN_INFO = build_mun_info(df, MUN_COL)
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

GEO_UF = GEO_MIC = None
if SEM_MALHA:
    print("--sem-malha: geo_uf.json e geo_mic.json ficam como estão")
else:
    print("Downloading GeoJSON (parallel) …")
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
    # parte → total que já a contém: selecionável sozinha, fora de toda soma
    "filhas":         FILHAS,
    # cultura → nome do arquivo em pam_mun/ (sem acento, para a URL)
    "arq_cultura":    ARQ_CULTURA,
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
# allow_nan=False: NaN no arquivo faria o navegador recusar o pkg.json inteiro
OUT_PKG.write_text(json.dumps(PKG, ensure_ascii=False, separators=(',',':'), allow_nan=False), encoding="utf-8")
size = OUT_PKG.stat().st_size / 1_048_576
print(f"  pkg.json: {size:.1f} MB  ->  {OUT_PKG}")

if not SEM_MALHA:
    OUT_GEO_UF.write_text(json.dumps(GEO_UF, ensure_ascii=False, separators=(',',':'), allow_nan=False), encoding="utf-8")
    size = OUT_GEO_UF.stat().st_size / 1_048_576
    print(f"  geo_uf.json: {size:.1f} MB  ->  {OUT_GEO_UF}")

    OUT_GEO_MIC.write_text(json.dumps(GEO_MIC, ensure_ascii=False, separators=(',',':'), allow_nan=False), encoding="utf-8")
    size = OUT_GEO_MIC.stat().st_size / 1_048_576
    print(f"  geo_mic.json: {size:.1f} MB  ->  {OUT_GEO_MIC}")

print("\nDone! Deploy the public/ folder to Netlify.")
