"""Status/tamanho do CAR por UF: o que já tem validos+intersection e o que falta."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(BASE, "..", ".."))
GEO = os.path.join(ROOT, "data", "processed", "geospatial")
RAWCAR = os.path.join(ROOT, "data", "raw", "car")
UFS = ["AC","AL","AM","AP","BA","CE","DF","ES","GO","MA","MG","MS","MT","PA",
       "PB","PE","PI","PR","RJ","RN","RO","RR","RS","SC","SE","SP","TO"]

def dirsize_mb(p):
    t = 0
    for dp, _, fs in os.walk(p):
        for f in fs:
            try: t += os.path.getsize(os.path.join(dp, f))
            except OSError: pass
    return round(t / 1e6)

rows = []
for uf in UFS:
    val = os.path.exists(os.path.join(GEO, f"car_imoveis_validos_{uf}.parquet"))
    inter = os.path.exists(os.path.join(GEO, f"car_imovel_municipio_intersection_{uf}.parquet"))
    rawp = os.path.join(RAWCAR, uf)
    mb = dirsize_mb(rawp) if os.path.isdir(rawp) else 0
    status = "OK" if (val and inter) else ("VALIDOS_SO_SEM_INTER" if val else "FALTA")
    rows.append((uf, mb, val, inter, status))

falta = [r for r in rows if r[4] != "OK"]
falta.sort(key=lambda r: r[1])
print("=== COMPLETOS (validos+intersection) ===")
print(", ".join(r[0] for r in rows if r[4] == "OK"))
print(f"total completos: {sum(1 for r in rows if r[4]=='OK')}/27")
print("\n=== A REPROCESSAR (ascendente por MB) ===")
for uf, mb, val, inter, st in falta:
    print(f"  {uf:3} {mb:6}MB  validos={val} inter={inter}  -> {st}")
print("\nlista:", ",".join(r[0] for r in falta))
