# -*- coding: utf-8 -*-
# Item A: gera geo_mun.json (GO+TO) via IBGE Malhas API v3, chave cod_ibge (7 dig)
import urllib.request, json, ssl, gzip
from collections import Counter

UFS = {"52": "GO", "17": "TO"}
URL = ("https://servicodados.ibge.gov.br/api/v3/malhas/estados/{uf}"
       "?formato=application/vnd.geo+json&qualidade=intermediaria&intrarregiao=municipio")
OUT = r"C:\Users\schap\Claude\Projects\Agrocore (Estudos)\_build\geo_mun.json"

def _read(r):
    data = r.read()
    if r.info().get("Content-Encoding") == "gzip" or data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return json.loads(data.decode("utf-8"))

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "agrocore-pipeline", "Accept-Encoding": "identity"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return _read(r)
    except ssl.SSLError:
        ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=180, context=ctx) as r:
            return _read(r)

def clean_ring(ring):
    out = []
    for p in ring:
        if not out or out[-1] != p:
            out.append(p)
    if out and out[0] != out[-1]:
        out.append(out[0])
    return out if len(out) >= 4 else ring

def proc(geom):
    t, c = geom["type"], geom["coordinates"]
    r3 = lambda ring: clean_ring([[round(x, 3), round(y, 3)] for x, y in ring])
    if t == "Polygon":
        geom["coordinates"] = [r3(ring) for ring in c]
    elif t == "MultiPolygon":
        geom["coordinates"] = [[r3(ring) for ring in poly] for poly in c]
    return geom

feats = []
for uf, sig in UFS.items():
    gj = fetch(URL.format(uf=uf))
    fs = gj.get("features", [])
    print("UF", uf, sig, "features:", len(fs))
    if fs:
        print("  props exemplo:", fs[0].get("properties"))
    for f in fs:
        cod = str(f.get("properties", {}).get("codarea", "")).strip()
        f["properties"] = {"cod_ibge": cod, "uf": sig}
        f["geometry"] = proc(f["geometry"])
        feats.append(f)

with open(OUT, "w", encoding="utf-8") as fh:
    json.dump({"type": "FeatureCollection", "features": feats}, fh, ensure_ascii=False, separators=(",", ":"))
print("WROTE", OUT)
print("total features:", len(feats), "por UF:", dict(Counter(x["properties"]["uf"] for x in feats)))
print("cod_ibge amostra:", [x["properties"]["cod_ibge"] for x in feats[:3]], [x["properties"]["cod_ibge"] for x in feats[-3:]])
