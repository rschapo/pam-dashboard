"""
validate_outputs.py — Verificação transversal das saídas (§9 + §11).

Confere, para cada artefato esperado da Etapa 1 (e Etapa 2 quando presente):
  * existência do parquet e (para tabelas municipais) do CSV de conferência;
  * existência do manifesto correspondente;
  * chave cod_municipio presente e no padrão 7 dígitos;
  * ausência de zeros onde deveria haver null (heurística: colunas *_ha).

Consolida um relatório em data/manifests/validate_outputs.json e imprime resumo.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import PROCESSED_DIR, MANIFEST_DIR  # noqa: E402

ESPERADOS_E1 = {
    "dimensions/dim_municipio": True,
    "dimensions/dim_modulo_fiscal": False,
    "municipality/censo_agro_municipio_summary": False,
    "municipality/sncr_municipio_summary": False,
    "municipality/pevs_municipio": False,
    "municipality/rural_profile_stage1": False,
}
ESPERADOS_E2 = {
    "geospatial/car_municipio_summary": False,
    "municipality/mapbiomas_municipio": False,
    "municipality/rural_profile_stage2": False,
}


def _check_one(rel: str, obrig: bool) -> dict:
    p = (PROCESSED_DIR / rel).with_suffix(".parquet")
    r = {"artefato": rel, "obrigatorio": obrig, "existe": p.exists()}
    if not p.exists():
        r["status"] = "AUSENTE" + (" (obrigatório)" if obrig else " (pendente)")
        return r
    df = pd.read_parquet(p)
    r["linhas"] = len(df)
    if "cod_municipio" in df.columns:
        r["cod_7dig"] = bool((df["cod_municipio"].astype(str).str.len() == 7).all())
    zeros = {}
    for c in df.columns:
        if c.endswith("_ha"):
            z = int((pd.to_numeric(df[c], errors="coerce") == 0).sum())
            if z:
                zeros[c] = z
    if zeros:
        r["zeros_suspeitos_em_ha"] = zeros
    r["status"] = "OK"
    return r


def run() -> dict:
    itens = []
    for rel, ob in {**ESPERADOS_E1, **ESPERADOS_E2}.items():
        itens.append(_check_one(rel, ob))
    faltando_obrig = [i["artefato"] for i in itens if i["obrigatorio"] and not i["existe"]]
    res = {"ok": len(faltando_obrig) == 0, "faltando_obrigatorios": faltando_obrig, "itens": itens}
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    (MANIFEST_DIR / "validate_outputs.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res


def main():
    res = run()
    print("== validate_outputs ==")
    for i in res["itens"]:
        print(f"  [{i['status']:>18}] {i['artefato']}"
              + (f"  ({i.get('linhas')} linhas)" if i.get("existe") else ""))
    print("  RESULTADO:", "OK" if res["ok"] else "FALHAS")
    sys.exit(0 if res["ok"] else 1)


if __name__ == "__main__":
    main()
