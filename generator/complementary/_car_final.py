"""Compila a tabela final CAR (27 UFs) a partir dos manifests e verifica o summary."""
import os, sys, json, re
sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(BASE, "..", ".."))
MAN = os.path.join(ROOT, "data", "manifests")
GEO = os.path.join(ROOT, "data", "processed", "geospatial")
UFS = ["AC","AL","AM","AP","BA","CE","DF","ES","GO","MA","MG","MS","MT","PA",
       "PB","PE","PI","PR","RJ","RN","RO","RR","RS","SC","SE","SP","TO"]

def gv(warns, key):
    for w in warns or []:
        m = re.search(key + r"\D*(\d+)", str(w))
        if m: return int(m.group(1))
    return None

tot_im = tot_inv = tot_fora = 0
print(f"{'UF':<4}{'imóveis':>12}{'corrigidas':>12}{'fora_UF':>9}{'municípios':>12}")
print("-"*49)
rows = []
for uf in UFS:
    p = os.path.join(MAN, f"car_{uf}.json")
    if not os.path.exists(p):
        print(f"{uf:<4}{'FALTA MANIFEST':>12}")
        continue
    d = json.load(open(p, encoding="utf-8"))
    im = d.get("row_count") or 0
    mun = d.get("municipality_count") or 0
    warns = d.get("warnings", [])
    inv = gv(warns, "corrigidas") or 0
    fora = gv(warns, "fora da UF") or 0
    tot_im += im; tot_inv += inv; tot_fora += fora
    print(f"{uf:<4}{im:>12,}{inv:>12,}{fora:>9}{mun:>12,}")
print("-"*49)
print(f"{'TOT':<4}{tot_im:>12,}{tot_inv:>12,}{tot_fora:>9}")

sp = os.path.join(GEO, "car_municipio_summary.parquet")
s = pd.read_parquet(sp)
print(f"\ncar_municipio_summary: {len(s):,} linhas · "
      f"{s['cod_municipio'].nunique():,} municípios únicos · "
      f"{int(s['quantidade_cadastros'].sum()):,} cadastros somados")
print("colunas ambientais presentes:",
      [c for c in s.columns if any(k in c for k in
       ('consolidada','vegetacao','reserva','app','uso_restrito'))])
