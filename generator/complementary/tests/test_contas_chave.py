import json
import re

import pandas as pd
import pytest

import process_contas_chave as pc


def _base(linhas):
    cols = ["cnpj", "cnae_principal", "natureza_juridica", "capital_social"]
    df = pd.DataFrame(linhas, columns=cols)
    df["cnpj_basico"] = df["cnpj"].str[:8]
    return df


def _classes(df, anp=()):
    cls, excl = pc.classificar(df, set(anp))
    return dict(zip(cls["cnpj"], cls["setor"])), cls, excl


def test_so_natureza_empresarial_entra_e_a_exclusao_e_contada():
    s, _, excl = _classes(_base([
        ("11111111000101", "1071600", "2062", "5.000.000,00"),   # usina S.A.
        ("22222222000101", "0113000", "4120", "0,00"),           # produtor rural PF com CNAE de cana
        ("33333333000101", "0163600", "3999", "0,00"),           # associação
        ("44444444000101", "0163600", "2240", "10.000,00"),      # sociedade simples limitada
    ]))
    assert s == {"11111111000101": "usina", "44444444000101": "pos_colheita"}
    assert excl == {"excluidos_produtor_rural_pf": 1, "excluidos_outras_naturezas": 1,
                    "excluidos_usina_sem_anp_capital_menor_1mi": 0}


def test_capital_minimo_vale_para_sucos_e_eucalipto_mas_nao_para_celulose():
    s, _, _ = _classes(_base([
        ("10000000000101", "1033301", "2062", "1.000.000,00"),   # suco, no limite: entra
        ("10000001000101", "1033301", "2062", "999.999,99"),     # suco pequeno: fora
        ("10000002000101", "0210101", "2062", "2.500.000,00"),   # eucalipto grande
        ("10000003000101", "0210101", "2062", "50.000,00"),      # eucalipto pequeno: fora
        ("10000004000101", "1710900", "2062", "1.000,00"),       # celulose: qualquer capital
        ("10000005000101", "0210101", "2062", None),             # capital ausente: fora
    ]))
    assert s == {"10000000000101": "sucos", "10000002000101": "florestal", "10000004000101": "florestal"}


def test_unidade_agricola_so_com_raiz_de_usina():
    s, _, _ = _classes(_base([
        ("55555555000101", "1071600", "2062", "3.000.000,00"),
        ("55555555000282", "0113000", "2062", "3.000.000,00"),   # fazenda do mesmo grupo
        ("66666666000101", "0113000", "2062", "1,00"),   # fazenda de quem não tem usina: fora
    ]))
    assert s == {"55555555000101": "usina", "55555555000282": "usina_agricola"}


def test_planta_da_anp_com_outro_cnae_entra_e_usina_sem_anp_fica_para_confirmar():
    _, cls, _ = _classes(_base([
        ("77777777000101", "0113000", "2062", "1,00"),   # ANP, registrada como fazenda de cana
        ("88888888000101", "1931400", "2062", "1.500.000,00"),   # CNAE de álcool sem autorização
        ("99999999000101", "1072401", "2062", "1,00"),   # CNAE de açúcar com autorização
    ]), anp={"77777777000101", "99999999000101"})
    r = cls.set_index("cnpj")
    assert r.loc["77777777000101", "setor"] == "usina" and not r.loc["77777777000101", "confirmar"]
    assert r.loc["88888888000101", "confirmar"]
    assert not r.loc["99999999000101", "confirmar"]
    assert pc.setor_painel(cls).tolist() == ["usina_anp", "usina_conf", "usina_anp"]


def test_usina_sem_anp_so_fica_para_confirmar_com_capital_de_1_mi():
    """Abaixo de R$ 1 mi, CNAE de açúcar ou álcool sem a ANP é, quase sempre, fabricante de
    melado, açúcar mascavo ou álcool artesanal: fica fora, e a fazenda dele não vira unidade
    agrícola de grupo. Com autorização da ANP, o capital não importa."""
    s, _, excl = _classes(_base([
        ("30000000000101", "1071600", "2062", "10.000,00"),      # açúcar mascavo: fora
        ("30000000000282", "0113000", "2062", "10.000,00"),      # a fazenda dele: fora também
        ("31000000000101", "1931400", "2062", None),             # capital ausente: fora
        ("32000000000101", "1071600", "2062", "1.000.000,00"),   # no limite: confirmar
        ("33000000000101", "1931400", "2062", "5.000,00"),       # pequena, mas autorizada na ANP
    ]), anp={"33000000000101"})
    assert s == {"32000000000101": "usina", "33000000000101": "usina"}
    assert excl["excluidos_usina_sem_anp_capital_menor_1mi"] == 2


def test_cooperativa_pela_natureza_2143_so_nas_divisoes_01_10_46():
    s, _, _ = _classes(_base([
        ("12121212000101", "4623109", "2143", "1,00"),   # cooperativa atacadista agro
        ("13131313000101", "6422100", "2143", "1,00"),   # cooperativa de crédito: fora
        ("14141414000101", "0151201", "2143", "1,00"),
    ]))
    assert s == {"12121212000101": "cooperativa", "14141414000101": "cooperativa"}


def test_agregado_soma_capacidade_so_das_plantas_anp():
    _, cls, _ = _classes(_base([
        ("20000000000101", "1071600", "2062", "1,00"),
        ("20000000000282", "1071600", "2062", "1,00"),
        ("21000000000101", "1931400", "2062", "1.000.000,00"),
    ]), anp={"20000000000101", "20000000000282"})
    cls["cod_municipio"] = "3550308"
    ag = pc.agregar(cls, {"20000000000101": 500.0, "20000000000282": 250.0}).set_index("setor")
    assert ag.loc["usina_anp", "estabelecimentos"] == 2
    assert ag.loc["usina_anp", "cap_etanol_m3d"] == 750
    assert ag.loc["usina_conf", "estabelecimentos"] == 1 and pd.isna(ag.loc["usina_conf", "cap_etanol_m3d"])


def test_json_publico_das_contas_so_tem_agregado():
    p = pc.PUBLIC_DATA / "contas_chave.json"
    if not p.exists():
        pytest.skip("contas_chave.json ainda não gerado (process_contas_chave.py)")
    c = json.loads(p.read_text(encoding="utf-8"))
    setores = set(c["setores"])
    assert setores == {"usina_anp", "usina_conf", "usina_agricola", "sucos", "pos_colheita",
                       "cafe", "florestal", "cooperativa"}
    for cod, o in c["mun"].items():
        assert re.fullmatch(r"[1-5]\d{6}", cod)
        assert set(o) <= setores | {"xy", "cap"}
        assert all(isinstance(o[k], int) and o[k] > 0 for k in o if k in setores)
    # os totais do cabeçalho são a soma dos municípios
    for s in setores:
        assert c["totais"][s] == sum(o.get(s, 0) for o in c["mun"].values())
    # a validação é só de contagens
    assert all(isinstance(v, (int, str)) for v in c["validacao"].values())
