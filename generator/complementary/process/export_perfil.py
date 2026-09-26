"""
export_perfil.py — gera o JSON do quadro "Perfil do município" do dashboard.

Grava public/data/perfil.json, lido sob demanda quando se escolhe um município na
visão Municípios, em qualquer aba. Junta num registro por município o que as bases
complementares dizem dele:
  - módulo fiscal e fração mínima de parcelamento (INCRA, IE nº 5/2022);
  - CAR: imóveis cadastrados, sobreposição e a estrutura fundiária — % dos imóveis e
    % da área em pequenos (até 4 MF), médios (4 a 15) e grandes (acima de 15);
  - Censo Agropecuário 2017: estabelecimentos e a área deles;
  - MapBiomas: agricultura, pastagem e silvicultura, em ha;
  - PEVS: valor da silvicultura e o produto predominante.

Tudo sai do rural_profile_stage2 (build_rural_profile.py), que já tem essas
colunas, mais a FMP (dim_modulo_fiscal) e a área municipal (dim_municipio). O perfil
completo (data/frontend/perfil_rural.json) pesa quase 5 MB; este leva só o que o
quadro mostra, com chaves curtas e sem os campos nulos. Campo ausente é "sem dado",
nunca zero.

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

# chave no JSON → (coluna, casas decimais); área e valor em inteiro, percentuais com 1 casa
CAMPOS = {
    "mf": ("modulo_fiscal_ha", 0),
    "fmp": ("fracao_minima_parcelamento_ha", 1),
    "amun": ("area_municipal_ha", 0),
    "imov": ("quantidade_cadastros_car", 0),
    "sob": ("percentual_sobreposicao_car", 1),
    "est": ("numero_estabelecimentos_censo", 0),
    "aest": ("area_estabelecimentos_censo_ha", 0),
    "agri": ("mapbiomas_agricultura_ha", 0),
    "past": ("mapbiomas_pastagem_ha", 0),
    "silv": ("mapbiomas_silvicultura_ha", 0),
    "vpf": ("valor_producao_florestal", 0),
}
# estrutura fundiária: [pequenos, médios, grandes] em % dos imóveis e em % da área
ESTRUTURA = {
    "en": ["percentual_pequenos_imoveis_car", "percentual_medios_imoveis_car",
           "percentual_grandes_imoveis_car"],
    "ea": ["percentual_area_pequenos_imoveis_car", "percentual_area_medios_imoveis_car",
           "percentual_area_grandes_imoveis_car"],
}


def _num(v, casas: int):
    if v is None or pd.isna(v):
        return None
    f = float(v)
    if math.isinf(f):
        return None
    return int(round(f)) if casas == 0 else round(f, casas)


def registro(r: pd.Series) -> dict:
    """Um município, só com os campos que ele tem."""
    reg = {}
    for chave, (col, casas) in CAMPOS.items():
        v = _num(r.get(col), casas)
        if v is not None:
            reg[chave] = v
    for chave, cols in ESTRUTURA.items():
        vals = [_num(r.get(c), 1) for c in cols]
        if all(v is not None for v in vals):
            reg[chave] = vals
    if isinstance(r.get("produto_florestal_predominante"), str):
        reg["ppf"] = r["produto_florestal_predominante"]
    return reg


def build_perfil() -> dict:
    prof = pd.read_parquet(PROCESSED_DIR / "municipality" / "rural_profile_stage2.parquet")
    dims = PROCESSED_DIR / "dimensions"
    dim = pd.read_parquet(dims / "dim_municipio.parquet", columns=["cod_municipio", "area_municipal_ha"])
    prof = prof.merge(dim, on="cod_municipio", how="left")
    mf = dims / "dim_modulo_fiscal.parquet"
    if mf.exists():
        prof = prof.merge(pd.read_parquet(mf, columns=["cod_municipio", "fracao_minima_parcelamento_ha"]),
                          on="cod_municipio", how="left")
    mun = {}
    for _, r in prof.iterrows():
        reg = registro(r)
        if reg:
            mun[str(r["cod_municipio"])] = reg
    mb = PROCESSED_DIR / "municipality" / "mapbiomas_municipio.parquet"
    anos = {"censo": 2017,
            "mapbiomas": int(pd.read_parquet(mb, columns=["ano"])["ano"].max()) if mb.exists() else None,
            "pevs": int(prof["ano_referencia_pevs"].dropna().iloc[0])
            if "ano_referencia_pevs" in prof and prof["ano_referencia_pevs"].notna().any() else None}
    return {"fonte": "INCRA, SICAR, IBGE (Censo Agro, PEVS), MapBiomas", "anos": anos,
            "gerado_em": now_iso(), "mun": mun}


def main():
    obj = build_perfil()
    PUBLIC_DATA.mkdir(parents=True, exist_ok=True)
    p = PUBLIC_DATA / "perfil.json"
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    cobertura = {c: sum(1 for m in obj["mun"].values() if c in m)
                 for c in list(CAMPOS) + list(ESTRUTURA) + ["ppf"]}
    print(f"  perfil.json: {len(obj['mun']):,} municípios · {p.stat().st_size / 1_048_576:.2f} MB · anos {obj['anos']}")
    print(f"    cobertura: {cobertura}")


if __name__ == "__main__":
    main()
