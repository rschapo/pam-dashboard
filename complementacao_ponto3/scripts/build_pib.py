# -*- coding: utf-8 -*-
# Item C (ajustado a disponibilidade IBGE): PIB total 2021-2023 + abertura VAB 2021 (ultimo ano com setorial)
import urllib.request, json, ssl, gzip, csv

UFS = {"52": "GO", "17": "TO"}
VARS = ["37", "498", "513", "517", "525", "6575", "543"]  # PIB, VABtot, agro, ind, admpub, serv, impostos
PERIODS = "2021,2022,2023"
OUTD = r"C:\Users\schap\Claude\Projects\Agrocore (Estudos)\_build"
FONTE = ("IBGE/SIDRA tabela 5938 (PIB dos Municipios). PIB total disponivel ate 2023; "
         "abertura de VAB por setor disponivel ate 2021 (2022/2023 ainda nao publicados pelo IBGE).")

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "agrocore", "Accept-Encoding": "identity"})
    try:
        r = urllib.request.urlopen(req, timeout=180)
    except ssl.SSLError:
        ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        r = urllib.request.urlopen(req, timeout=180, context=ctx)
    d = r.read()
    if r.info().get("Content-Encoding") == "gzip" or d[:2] == b"\x1f\x8b":
        d = gzip.decompress(d)
    return json.loads(d.decode("utf-8"))

def num(v):
    if v is None: return None
    s = str(v).strip().replace(" ", "")
    if s in {"", "-", "..", "...", "X", "-0"}: return None
    if "," in s and "." in s: s = s.replace(".", "").replace(",", ".")
    elif "," in s: s = s.replace(",", ".")
    try:
        f = float(s); return int(f) if f == int(f) else f
    except ValueError: return None

def parse(rows):
    h = rows[0]
    def find(pred): return next((k for k, lab in h.items() if pred(lab.lower())), None)
    tcode = find(lambda l: "(código)" in l and ("município" in l or "unidade da federação" in l))
    tname = find(lambda l: l in ("município", "unidade da federação"))
    vcode = find(lambda l: l == "variável (código)")
    ycode = find(lambda l: l in ("ano (código)", "ano"))
    recs = {}
    for row in rows[1:]:
        tc = row[tcode]
        rec = recs.setdefault(tc, {"municipio": row.get(tname, "")})
        rec[(row[vcode], row[ycode])] = num(row.get("V"))
    return recs

def rowify(recs, is_uf):
    out = []
    for code in sorted(recs):
        r = recs[code]
        uf = UFS.get(code) if is_uf else UFS.get(code[:2])
        g = lambda v, y="2021": r.get((v, y))
        pib21, agro21 = g("37"), g("513")
        pct = round(agro21 / pib21 * 100, 2) if (pib21 and agro21) else None
        rec = {("uf_cod" if is_uf else "cod_ibge"): code, "uf": uf}
        if not is_uf: rec["municipio"] = r["municipio"]
        rec.update({
            "pib_2021_mil_reais": g("37", "2021"),
            "pib_2022_mil_reais": g("37", "2022"),
            "pib_2023_mil_reais": g("37", "2023"),
            "vab_total_2021_mil_reais": g("498"),
            "vab_agropecuaria_2021_mil_reais": g("513"),
            "vab_industria_2021_mil_reais": g("517"),
            "vab_servicos_2021_mil_reais": g("6575"),
            "vab_adm_publica_2021_mil_reais": g("525"),
            "impostos_2021_mil_reais": g("543"),
            "pct_agro_no_pib_2021": pct,
            "ano_pib_mais_recente": "2023",
            "ano_vab": "2021",
            "fonte": FONTE,
        })
        out.append(rec)
    return out

def wcsv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), delimiter=";")
        w.writeheader(); w.writerows(rows)

BASE = "https://apisidra.ibge.gov.br/values/t/5938/{lvl}/v/" + ",".join(VARS) + "/p/" + PERIODS
mrecs = {}
for uf in UFS:
    mrecs.update(parse(fetch(BASE.format(lvl="n6/in%20n3%20" + uf))))
    print("mun UF", uf, "acumulado:", len(mrecs))
mrows = rowify(mrecs, False)
wcsv(OUTD + r"\mun_demografia_pib.csv", mrows)
urows = rowify(parse(fetch(BASE.format(lvl="n3/52,17"))), True)
wcsv(OUTD + r"\uf_demografia_pib.csv", urows)

print("WROTE mun:", len(mrows), "| uf:", len(urows))
for r in urows:
    print("UF", r["uf"], "PIB2023", r["pib_2023_mil_reais"], "VABagro2021", r["vab_agropecuaria_2021_mil_reais"], "pctAgro2021", r["pct_agro_no_pib_2021"])
print("amostra mun:", {k: mrows[0][k] for k in list(mrows[0])[:8]})
