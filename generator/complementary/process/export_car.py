"""
export_car.py — gera o JSON do Cadastro Ambiental Rural para o dashboard.

Grava public/data/car.json com o resumo municipal do CAR: quantos imóveis rurais
estão cadastrados, o tamanho típico da propriedade, quanto do território está
declarado e quanto os cadastros se sobrepõem entre si.

Dois cortes de qualidade, porque o dado bruto não se sustenta em todos os casos:

  1. O Distrito Federal sai inteiro. A base traz 1 único imóvel para Brasília,
     o que indica download incompleto, não ausência de agricultura.
  2. A área declarada é omitida onde a soma passa de 105% da área do município.
     Um imóvel que cruza divisas é atribuído por inteiro ao município onde está
     a maior parte dele, então municípios vizinhos de grandes propriedades
     acumulam área que fisicamente não cabe neles.

Omitir é deliberado: o campo ausente aparece como "sem dado" no painel, em vez
de um número que o usuário leria como medição.

A área típica do imóvel sai como média (área ÷ imóveis) e não como mediana: a
mediana municipal não se recompõe em estado nem em microrregião, e o painel
precisa do mesmo indicador nos três níveis.

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

UF_EXCLUIDA = "DF"
COBERTURA_MAX = 1.05


def _num(v):
    if v is None:
        return None
    f = float(v)
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, 2) if f % 1 else int(f)


def build_car() -> dict:
    car = pd.read_parquet(PROCESSED_DIR / "geospatial" / "car_municipio_summary.parquet")
    dim = pd.read_parquet(PROCESSED_DIR / "dimensions" / "dim_municipio.parquet")
    d = car.merge(dim[["cod_municipio", "uf", "area_municipal_ha"]],
                  on="cod_municipio", how="left")

    n_total = len(d)
    d = d[d["uf"] != UF_EXCLUIDA]
    n_uf_fora = n_total - len(d)

    d["cobertura"] = d["area_geometrica_uniao_ha"] / d["area_municipal_ha"]
    area_implausivel = d["cobertura"] > COBERTURA_MAX

    # Território declarado, área média e sobreposição são razões. O JSON carrega
    # os componentes para que estado e microrregião recomponham cada uma a partir
    # das somas — somar percentuais daria o estado como soma das taxas.
    mun: dict[str, dict] = {}
    for r in d.itertuples(index=False):
        reg = {"imov": _num(r.quantidade_cadastros),
               "_asob": _num(r.area_sobreposta_ha),
               "_abru": _num(r.area_geometrica_bruta_ha)}
        if r.cobertura is not None and r.cobertura <= COBERTURA_MAX:
            reg["area"] = _num(r.area_geometrica_uniao_ha)
            reg["_amun"] = _num(r.area_municipal_ha)
        mun[str(r.cod_municipio)] = reg

    return {
        "fonte": "SICAR — Cadastro Ambiental Rural",
        "campos": {
            "imov": "Imóveis rurais cadastrados",
            "area": "Área declarada (ha)",
            "cob": "Território declarado (%)",
            "amed": "Área média do imóvel (ha)",
            "sobre": "Sobreposição entre cadastros (%)",
        },
        "razoes": {
            "cob": {"num": "area", "den": "_amun", "fator": 100},
            "amed": {"num": "area", "den": "imov", "fator": 1},
            "sobre": {"num": "_asob", "den": "_abru", "fator": 100},
        },
        "ressalvas": {
            "uf_excluida": UF_EXCLUIDA,
            "municipios_sem_uf": int(n_uf_fora),
            "area_omitida": int(area_implausivel.sum()),
        },
        "gerado_em": now_iso(),
        "mun": mun,
    }


def main():
    obj = build_car()
    PUBLIC_DATA.mkdir(parents=True, exist_ok=True)
    p = PUBLIC_DATA / "car.json"
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    r = obj["ressalvas"]
    print(f"  car.json: {len(obj['mun']):,} municípios · {p.stat().st_size / 1_048_576:.2f} MB")
    print(f"    {r['municipios_sem_uf']} municípios de {r['uf_excluida']} fora (base incompleta)")
    print(f"    área omitida em {r['area_omitida']} municípios (soma excede o território)")


if __name__ == "__main__":
    main()
