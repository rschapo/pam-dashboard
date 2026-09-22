import pandas as pd

import process_sncr as ps
import _stats as st


def _validos():
    # imóveis sintéticos em um município fictício
    return pd.DataFrame([
        {"cod_municipio": "5107925", "uf": "MT", "area_total_ha": 30.0,
         "numero_modulos_fiscais": 0.5, "faixa_modulo_analitica": st.faixa_mf(0.5),
         "faixa_modulo_legal": st.faixa_mf(0.5, st.FAIXAS_MF_LEGAL),
         "flag_area_zero": False, "flag_duplicidade": False},
        {"cod_municipio": "5107925", "uf": "MT", "area_total_ha": 600.0,
         "numero_modulos_fiscais": 10.0, "faixa_modulo_analitica": st.faixa_mf(10.0),
         "faixa_modulo_legal": st.faixa_mf(10.0, st.FAIXAS_MF_LEGAL),
         "flag_area_zero": False, "flag_duplicidade": False},
        {"cod_municipio": "5107925", "uf": "MT", "area_total_ha": 5000.0,
         "numero_modulos_fiscais": 83.3, "faixa_modulo_analitica": st.faixa_mf(83.3),
         "faixa_modulo_legal": st.faixa_mf(83.3, st.FAIXAS_MF_LEGAL),
         "flag_area_zero": False, "flag_duplicidade": False},
    ])


def test_hash_determinista_e_anonimo():
    h1 = ps._hash_id("BR-5107925-XYZ")
    h2 = ps._hash_id("BR-5107925-XYZ")
    assert h1 == h2 and len(h1) == 24
    assert "5107925" not in h1  # não expõe o id original


def test_summary_quantidade_e_area_sao_distintos():
    s = ps._summary(_validos())
    row = s.iloc[0]
    # 3 imóveis: 1 pequeno (<=4mf), 1 médio (4-15mf), 1 grande (>15mf)
    assert row["quantidade_imoveis_total"] == 3
    assert row["percentual_imoveis_ate_4_mf"] == pytest.approx(33.33, abs=0.1)
    # por ÁREA, o grande domina — % área <=4mf deve ser pequeno e != % imóveis
    assert row["percentual_area_ate_4_mf"] < row["percentual_imoveis_ate_4_mf"]
    assert row["coeficiente_gini_area"] is not None


import pytest  # noqa: E402
