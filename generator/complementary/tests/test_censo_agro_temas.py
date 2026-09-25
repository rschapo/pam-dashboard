"""Os temas do Censo Agro 2017 como saem nas tabelas processadas.

Os brutos de 07/08 perderam a categoria (o coletor não achava a coluna da
classificação), e parte dos temas apontava para a tabela ou a classificação erradas:
a armazenagem vinha da 6875, que é de veículos. Os totais do Brasil foram conferidos
na SIDRA, no nível Brasil, em 25/09/2026.
"""
import pandas as pd
import pytest

import process_censo_agro as pc

NUM_ESTAB = "Número de estabelecimentos agropecuários"
AREA_ESTAB = "Área dos estabelecimentos agropecuários"
ESTAB_BRASIL = 5_073_324
AREA_BRASIL_HA = 351_289_816


def _tema(tema):
    p = pc.PROCESSED_DIR / "municipality" / f"censo_agro_{tema}.parquet"
    if not p.exists():
        pytest.skip(f"censo_agro_{tema} ausente")
    return pd.read_parquet(p)


@pytest.mark.parametrize("tema", pc.TEMAS)
def test_cada_linha_tem_a_sua_categoria(tema):
    """Sem a categoria, as linhas de um município viravam cópias indistinguíveis."""
    df = _tema(tema)
    assert (df["subcategoria"].fillna("") != "").all()
    assert not df.duplicated(["cod_municipio", "variavel", "subcategoria"]).any()


@pytest.mark.parametrize("tema, variavel, total_brasil", [
    ("area_groups", NUM_ESTAB, ESTAB_BRASIL),
    ("family_farming", NUM_ESTAB, ESTAB_BRASIL),
    ("land_condition", NUM_ESTAB, ESTAB_BRASIL),
    ("technical_assistance", NUM_ESTAB, ESTAB_BRASIL),
    ("activity", NUM_ESTAB, ESTAB_BRASIL),
    ("area_groups", AREA_ESTAB, AREA_BRASIL_HA),
    ("land_use", AREA_ESTAB, AREA_BRASIL_HA),
    ("irrigation", "Área irrigada dos estabelecimentos agropecuários", 6_694_245),
    ("storage", "Capacidade das unidades armazenadoras", 56_521_431),
    ("finance", "Número de estabelecimentos agropecuários que obtiveram financiamento", 784_538),
])
def test_linha_total_dos_municipios_fecha_com_o_brasil(tema, variavel, total_brasil):
    """Somar o Total dos municípios dá o Brasil. Só o sigilo tira alguma coisa: o IBGE
    suprime (X) o Total de alguns municípios, e aí a soma fica abaixo. Em 25/09/2026 o
    que mais perdia era a capacidade de armazenagem, 1,1% (728 municípios suprimidos)."""
    df = _tema(tema)
    tot = df[(df["subcategoria"] == "Total") & (df["variavel"].str.strip() == variavel)]
    assert tot["cod_municipio"].is_unique
    soma, suprimidos = tot["valor"].sum(), tot["valor"].isna().sum()
    if suprimidos:
        assert total_brasil * 0.98 < soma < total_brasil
    else:
        assert soma == total_brasil


@pytest.mark.parametrize("tema, categorias", [
    ("family_farming", {"Agricultura familiar - sim", "Agricultura familiar - não"}),
    ("technical_assistance", {"Recebe", "Não recebe"}),
    ("storage", {"Silos", "Armazéns convencionais e estruturais"}),
    ("area_groups", {"Produtor sem área", "De 10.000 ha e mais"}),
])
def test_tema_abre_pela_classificacao_da_descricao(tema, categorias):
    assert categorias <= set(_tema(tema)["subcategoria"])


def test_harmoniza_as_classes_de_500_ha_para_cima_com_os_nomes_do_sidra():
    """O mapa de faixas escrevia "1000" e "2500" sem o ponto e tinha uma classe única
    acima de 2.500 ha; no SIDRA são "1.000" e "2.500", e acima de 2.500 ha há duas
    classes. As faixas de 500 ha para cima ficavam fora da harmonização."""
    area = pd.DataFrame([{"cod_municipio": "5107925", "subcategoria": s, "variavel": NUM_ESTAB, "valor": v}
                         for s, v in [("De 500 a menos de 1.000 ha", 100), ("De 1.000 a menos de 2.500 ha", 130),
                                      ("De 2.500 a menos de 10.000 ha", 98), ("De 10.000 ha e mais", 7)]])
    harm = pc.harmonizar_area_groups(area).set_index("faixa_harmonizada")["valor"]
    assert harm.to_dict() == {"mais_500_ate_1000_ha": 100, "mais_1000_ha": 235}


def _classes(*linhas):
    return pd.DataFrame([{"cod_municipio": "3500105", "subcategoria": s, "variavel": AREA_ESTAB, "valor": v}
                         for s, v in linhas])


def test_faixa_com_classe_nula_que_era_zero_soma_normalmente():
    """O coletor grava como nulo o "-" do SIDRA, que é zero. Quando as classes do
    município fecham com o Total, todo nulo era zero e a faixa se reconstrói."""
    harm = pc.harmonizar_area_groups(_classes(
        ("Total", 1030), ("De 1 a menos de 2 ha", 10), ("De 2 a menos de 3 ha", None),
        ("De 5 a menos de 10 ha", 20), ("De 50 a menos de 100 ha", 1000), ("Produtor sem área", None),
    )).set_index("faixa_harmonizada")["valor"]
    assert harm.to_dict() == {"ate_10_ha": 30, "mais_50_ate_100_ha": 1000}


def test_faixa_com_classe_sigilosa_fica_nula():
    """O "X" do SIDRA (sigilo) também chega nulo. Quando as classes não fecham com o
    Total, algum nulo esconde área: a faixa que tem classe nula não se reconstrói, e as
    outras continuam."""
    harm = pc.harmonizar_area_groups(_classes(
        ("Total", 1500), ("De 1 a menos de 2 ha", 10), ("De 2 a menos de 3 ha", None),
        ("De 5 a menos de 10 ha", 20), ("De 50 a menos de 100 ha", 1000), ("Produtor sem área", None),
    )).set_index("faixa_harmonizada")["valor"]
    assert pd.isna(harm["ate_10_ha"])
    assert harm["mais_50_ate_100_ha"] == 1000
