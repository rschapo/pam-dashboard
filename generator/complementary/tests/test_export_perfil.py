import json

import pandas as pd
import pytest

import export_perfil as ep


def test_registro_arredonda_e_deixa_de_fora_o_que_falta():
    r = pd.Series({"modulo_fiscal_ha": 90.0, "fracao_minima_parcelamento_ha": 4.0,
                   "area_municipal_ha": 845483.4, "quantidade_cadastros_car": 2957.0,
                   "percentual_sobreposicao_car": 20.3456, "numero_estabelecimentos_censo": None,
                   "percentual_pequenos_imoveis_car": 73.29, "percentual_medios_imoveis_car": 21.11,
                   "percentual_grandes_imoveis_car": 5.6,
                   "percentual_area_pequenos_imoveis_car": 22.33, "percentual_area_medios_imoveis_car": None,
                   "percentual_area_grandes_imoveis_car": 38.35,
                   "produto_florestal_predominante": "1.2 - Lenha"})
    reg = ep.registro(r)
    assert reg == {"mf": 90, "fmp": 4.0, "amun": 845483, "imov": 2957, "sob": 20.3,
                   "en": [73.3, 21.1, 5.6], "ppf": "1.2 - Lenha"}
    # sem o Censo e com a área da estrutura incompleta: fora, e não zero


def test_registro_sem_nada_fica_vazio():
    assert ep.registro(pd.Series({"modulo_fiscal_ha": None, "produto_florestal_predominante": None})) == {}


def test_perfil_real_tem_todos_os_municipios_e_os_anos():
    p = ep.PUBLIC_DATA / "perfil.json"
    if not p.exists():
        pytest.skip("perfil.json ainda não gerado")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert len(d["mun"]) >= 5570 and d["anos"]["censo"] == 2017
    sorriso = d["mun"]["5107925"]
    assert sorriso["mf"] == 90 and len(sorriso["en"]) == len(sorriso["ea"]) == 3
    for m in d["mun"].values():
        for k in ("en", "ea"):
            if k in m:
                assert abs(sum(m[k]) - 100) <= 0.2     # três classes, arredondadas a 0,1
