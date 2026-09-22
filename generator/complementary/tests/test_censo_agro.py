import pandas as pd

import process_censo_agro as pc


def test_harmoniza_faixas_soma_compativeis():
    # duas classes originais que devem cair na mesma faixa harmonizada (ate_10_ha)
    area = pd.DataFrame([
        {"cod_municipio": "5107925", "ano_referencia": 2017, "categoria": "area_groups",
         "subcategoria": "De 1 a menos de 2 ha", "variavel": "Número de estabelecimentos",
         "valor": "10", "unidade": "un", "fonte_tabela_sidra": 6778},
        {"cod_municipio": "5107925", "ano_referencia": 2017, "categoria": "area_groups",
         "subcategoria": "De 5 a menos de 10 ha", "variavel": "Número de estabelecimentos",
         "valor": "15", "unidade": "un", "fonte_tabela_sidra": 6778},
        {"cod_municipio": "5107925", "ano_referencia": 2017, "categoria": "area_groups",
         "subcategoria": "De 50 a menos de 100 ha", "variavel": "Número de estabelecimentos",
         "valor": "4", "unidade": "un", "fonte_tabela_sidra": 6778},
    ])
    harm = pc.harmonizar_area_groups(area)
    ate10 = harm[(harm["faixa_harmonizada"] == "ate_10_ha")]["valor"].sum()
    faixa50 = harm[(harm["faixa_harmonizada"] == "mais_50_ate_100_ha")]["valor"].sum()
    assert ate10 == 25          # 10 + 15 somados só entre classes compatíveis
    assert faixa50 == 4


def test_produtor_sem_area_nao_entra_em_faixa():
    area = pd.DataFrame([
        {"cod_municipio": "5107925", "ano_referencia": 2017, "categoria": "area_groups",
         "subcategoria": "Produtor sem área", "variavel": "Número de estabelecimentos",
         "valor": "7", "unidade": "un", "fonte_tabela_sidra": 6778},
    ])
    harm = pc.harmonizar_area_groups(area)
    # 'Produtor sem área' é incompatível (compativel=0) -> não agrega em faixa de área
    assert harm.empty or "sem_area" not in set(harm["faixa_harmonizada"])
