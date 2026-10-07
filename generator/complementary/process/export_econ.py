"""
export_econ.py — gera public/data/econ.json (aba Economia do dashboard).

Lê demografia_pib (município e UF) de data/processed e grava, por município, os
componentes que o front soma por estado e microrregião:
  pop   população do ano do PIB, a que o IBGE usa no per capita (para 2023, a do
        Censo 2022, tabela 4709: não há estimativa de 2022 e 2023); ref_pop diz qual
  pib   PIB a preços correntes, mil R$ (ano_pib)
  agro  VAB da agropecuária, mil R$ (ano_vab)
  ind   VAB da indústria, mil R$ (ano_vab)
  serv  VAB dos serviços, exclusive administração pública, mil R$ (ano_vab)
  _vab  VAB total, mil R$ (ano_vab) — só denominador, não é métrica do seletor

As razões não vão prontas: o front recompõe o PIB per capita e a participação da
agropecuária dos componentes, em cada escopo (RAZOES_ECON em main.js), como faz
com as do car.json. A participação divide o VAB agro pelo VAB total do mesmo ano.
O IBGE publica o PIB municipal até 2023, mas a abertura por setor só até 2021, e
dividir o agro de 2021 pelo PIB de 2023 passava de 100% em municípios do RS, onde
a seca derrubou o PIB depois do ano recorde.

Município sem nenhum valor (Boa Esperança do Norte, instalado em 2025) fica fora;
o front o mostra como sem dado. O bloco "uf" traz os totais do IBGE por estado.

Nada aqui depende de rede.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import IBGE2UF, PROCESSED_DIR, now_iso  # noqa: E402

PUBLIC_DATA = Path(__file__).resolve().parents[3] / "public" / "data"

CAMPOS = {
    "populacao_pib": "pop",
    "pib_total": "pib",
    "vab_agropecuaria": "agro",
    "vab_industria": "ind",
    "vab_servicos": "serv",
    "vab_total": "_vab",
}


def _load(rel: str) -> pd.DataFrame:
    p = (PROCESSED_DIR / rel).with_suffix(".parquet")
    if not p.exists():
        raise SystemExit(f"{p.name} ausente em {p.parent}. Rode process_demografia_pib.py.")
    return pd.read_parquet(p)


def _num(v):
    if v is None:
        return None
    f = float(v)
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, 2) if f % 1 else int(f)


def _componentes(r) -> dict:
    d = {}
    for col, chave in CAMPOS.items():
        v = _num(getattr(r, col))
        if v is not None:
            d[chave] = v
    return d


def build_econ() -> dict:
    mun_df = _load("municipality/demografia_pib")
    uf_df = _load("state/demografia_pib")
    if "vab_total" not in mun_df:
        raise SystemExit("demografia_pib sem vab_total. Rode download_demografia_pib.py "
                         "e process_demografia_pib.py de novo.")

    mun = {}
    for r in mun_df.itertuples(index=False):
        d = _componentes(r)
        if d:
            mun[str(r.cod_ibge)] = d

    uf = {}
    for r in uf_df.itertuples(index=False):
        d = _componentes(r)
        if d:
            uf[IBGE2UF[str(r.cod_uf)]] = d

    return {
        "ano_pib": int(mun_df["ano_ref"].max()),
        "ano_vab": int(mun_df["ano_ref_vab"].max()),
        "ref_pop": str(mun_df["ref_populacao_pib"].dropna().iloc[0]),
        "fonte": "IBGE/SIDRA 5938 (PIB dos Municípios) + população do ano do PIB (6579 ou Censo 2022, 4709)",
        "gerado_em": now_iso(),
        "mun": mun,
        "uf": uf,
    }


def main():
    obj = build_econ()
    PUBLIC_DATA.mkdir(parents=True, exist_ok=True)
    p = PUBLIC_DATA / "econ.json"
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    mb = p.stat().st_size / 1_048_576
    print(f"  econ.json: {len(obj['mun']):,} municípios · {len(obj['uf'])} UF · "
          f"PIB {obj['ano_pib']} · VAB {obj['ano_vab']} · {mb:.2f} MB")


if __name__ == "__main__":
    main()
