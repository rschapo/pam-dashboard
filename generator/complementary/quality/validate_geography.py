"""
validate_geography.py — Controles de qualidade da dimensão territorial (§9.1).

Verifica dim_municipio:
  * código municipal com 7 dígitos;
  * UF compatível com os 2 primeiros dígitos do código;
  * ausência de duplicidade;
  * área municipal positiva quando preenchida (null é permitido, 0 não);
  * cobertura (nº de municípios) e nulos em campos-chave.

Retorna código de saída 0 se sem erros graves, 1 caso contrário. Também grava um
resumo em data/manifests/validate_geography.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import PROCESSED_DIR, MANIFEST_DIR, IBGE2UF  # noqa: E402


def run() -> dict:
    p = PROCESSED_DIR / "dimensions" / "dim_municipio.parquet"
    if not p.exists():
        return {"ok": False, "erros": ["dim_municipio.parquet ausente"]}
    df = pd.read_parquet(p)
    erros, avisos = [], []

    n7 = (df["cod_municipio"].astype(str).str.len() == 7).all()
    if not n7:
        erros.append("Há códigos municipais fora do padrão de 7 dígitos")

    uf_ok = df.apply(lambda r: IBGE2UF.get(str(r["cod_municipio"])[:2]) == r["uf"], axis=1).all()
    if not uf_ok:
        erros.append("Há municípios com UF incompatível com o código IBGE")

    dup = int(df["cod_municipio"].duplicated().sum())
    if dup:
        erros.append(f"{dup} código(s) municipal(is) duplicado(s)")

    area = pd.to_numeric(df["area_municipal_ha"], errors="coerce")
    zero_area = int((area == 0).sum())
    if zero_area:
        erros.append(f"{zero_area} município(s) com área = 0 (deveria ser null se ausente)")
    n_area = int(area.notna().sum())
    if n_area == 0:
        avisos.append("area_municipal_ha ausente para todos (IBGE Áreas Territoriais não carregada)")

    for col in ("uf", "nome_uf", "cod_regiao"):
        nn = int(df[col].isna().sum())
        if nn:
            erros.append(f"{nn} nulo(s) em {col}")

    res = {"ok": len(erros) == 0, "n_municipios": len(df), "duplicados": dup,
           "areas_preenchidas": n_area, "erros": erros, "avisos": avisos}
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    (MANIFEST_DIR / "validate_geography.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res


def main():
    res = run()
    print("== validate_geography ==")
    print(f"  municípios: {res.get('n_municipios')}  · duplicados: {res.get('duplicados')}")
    for e in res.get("erros", []):
        print(f"  [ERRO] {e}")
    for a in res.get("avisos", []):
        print(f"  [aviso] {a}")
    print("  RESULTADO:", "OK" if res.get("ok") else "FALHAS")
    sys.exit(0 if res.get("ok") else 1)


if __name__ == "__main__":
    main()
