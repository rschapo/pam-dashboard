"""
export_maquinas_credito.py — gera os JSONs de tratores e crédito rural para o dashboard.

Grava em public/data/ (consumidos pelo front sob demanda, como econ.json):
  maquinas.json — frota de tratores e estabelecimentos com trator, por faixa de
                  potência (Censo Agropecuário 2017, SIDRA 6870).
  credito.json  — crédito rural contratado por finalidade (BCB/SICOR).

Valores monetários saem em MIL R$, alinhados ao pkg.json (valor da produção) e ao
econ.json (PIB), para que o front possa comparar as três grandezas sem conversão.

Nada aqui depende de rede.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import PROCESSED_DIR, now_iso  # noqa: E402

PUBLIC_DATA = Path(__file__).resolve().parents[3] / "public" / "data"

# Rótulos da classificação "Potência dos tratores" (SIDRA 6870, c12605).
POT_TOTAL = "Total"
POT_MENOR = "Menos de 100 cv"
POT_MAIOR = "De 100 cv e mais"

VAR_ESTAB = "estabelecimentos agropecuários com tratores"
VAR_TRATORES = "tratores existentes"


def _load(rel: str) -> pd.DataFrame | None:
    p = (PROCESSED_DIR / rel).with_suffix(".parquet")
    return pd.read_parquet(p) if p.exists() else None


def _num(v):
    if v is None:
        return None
    f = float(v)
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, 2) if f % 1 else int(f)


def build_maquinas() -> dict:
    df = _load("municipality/censo_agro_machinery")
    if df is None or df.empty:
        raise SystemExit("censo_agro_machinery ausente. Rode process_censo_agro.py.")

    faltando = df[df["subcategoria"].isna() | (df["subcategoria"] == "")]
    if len(faltando):
        raise SystemExit(
            f"{len(faltando)} linhas sem rótulo de potência — rebaixe o tema machinery "
            "(o download precisa preservar a classificação c12605)."
        )

    ano = int(df["ano_referencia"].max())
    is_trator = df["variavel"].str.contains(VAR_TRATORES, case=False, na=False)
    is_estab = df["variavel"].str.contains(VAR_ESTAB, case=False, na=False)

    campos = {
        "trat":   (is_trator, POT_TOTAL),
        "trat_p": (is_trator, POT_MENOR),
        "trat_g": (is_trator, POT_MAIOR),
        "est":    (is_estab,  POT_TOTAL),
    }

    mun: dict[str, dict] = {}
    for nome, (mask, pot) in campos.items():
        sub = df[mask & (df["subcategoria"] == pot)]
        for cod, val in zip(sub["cod_municipio"], sub["valor"]):
            v = _num(val)
            if v:
                mun.setdefault(str(cod), {})[nome] = v

    return {
        "ano": ano,
        "fonte": "IBGE/Censo Agropecuário 2017 — SIDRA 6870",
        "campos": {
            "trat": "Frota de tratores",
            "trat_p": "Tratores — menos de 100 cv",
            "trat_g": "Tratores — 100 cv ou mais",
            "est": "Estabelecimentos com trator",
        },
        "gerado_em": now_iso(),
        "mun": mun,
    }


def build_credito() -> dict:
    df = _load("municipality/credito_rural")
    if df is None or df.empty:
        raise SystemExit("credito_rural ausente. Rode process_credito_rural.py.")

    ano = int(df["ano_ref"].max())
    cur = df[df["ano_ref"] == ano]

    mun: dict[str, dict] = {}
    for r in cur.itertuples(index=False):
        cod = str(r.cod_ibge)
        d = mun.setdefault(cod, {})
        # SICOR publica em reais; o dashboard trabalha em mil R$.
        valor = _num((r.valor_contratado or 0) / 1000)
        area = _num(r.area_ha)
        chave = "cust" if r.finalidade == "Custeio" else "inv"
        if valor:
            d[chave] = valor
            d["total"] = _num((d.get("total") or 0) + valor)
        if area:
            d["area"] = _num((d.get("area") or 0) + area)

    return {
        "ano": ano,
        "fonte": "BCB/SICOR (MDCR)",
        "campos": {
            "total": "Crédito total contratado (mil R$)",
            "cust": "Custeio (mil R$)",
            "inv": "Investimento (mil R$)",
            "area": "Área financiada (ha)",
        },
        "gerado_em": now_iso(),
        "mun": mun,
    }


def _write(name: str, obj: dict) -> str:
    PUBLIC_DATA.mkdir(parents=True, exist_ok=True)
    p = PUBLIC_DATA / name
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    mb = p.stat().st_size / 1_048_576
    print(f"  {name}: {len(obj['mun']):,} municípios · ano {obj['ano']} · {mb:.2f} MB")
    return str(p)


def main():
    _write("maquinas.json", build_maquinas())
    _write("credito.json", build_credito())
    print("[EXPORT] maquinas.json + credito.json em public/data/")


if __name__ == "__main__":
    main()
