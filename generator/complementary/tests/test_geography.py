import math
from pathlib import Path

import pandas as pd
import pytest

import common
import _stats as st

ROOT = Path(__file__).resolve().parents[3]  # pam-dashboard
DIM = ROOT / "data" / "processed" / "dimensions" / "dim_municipio.parquet"


def test_cod_mun7_normaliza():
    assert common.cod_mun7("1100015") == "1100015"
    assert common.cod_mun7(1100015) == "1100015"
    assert common.cod_mun7("1100015.0") == "1100015"
    assert common.cod_mun7("35") is None          # curto demais
    assert common.cod_mun7("") is None
    assert common.cod_mun7(None) is None


def test_uf_from_cod():
    assert common.uf_from_cod("3550308") == "SP"
    assert common.uf_from_cod("5107925") == "MT"
    assert common.uf_from_cod("1100015") == "RO"


def test_clean_num_nulos_nunca_zero():
    assert common.clean_num("-") is None
    assert common.clean_num("..") is None
    assert common.clean_num("X") is None
    assert common.clean_num("1234") == 1234.0
    assert common.clean_num("1.234,56") == pytest.approx(1234.56)


def test_gini_valores_conhecidos():
    assert st.gini([10, 10, 10, 10]) == 0.0
    assert st.gini([1, 2, 3, 4, 5]) == pytest.approx(0.2667, abs=1e-3)
    assert st.gini([5]) is None


def test_faixa_modulo_fiscal():
    assert st.faixa_mf(0.5) == "ate_1_mf"
    assert st.faixa_mf(1.0) == "ate_1_mf"
    assert st.faixa_mf(3.9) == "mais_2_ate_4_mf"
    assert st.faixa_mf(60) == "mais_50_mf"
    assert st.faixa_mf(None) is None
    assert st.faixa_mf(4.0, st.FAIXAS_MF_LEGAL) == "ate_4_mf"
    assert st.faixa_mf(20.0, st.FAIXAS_MF_LEGAL) == "mais_15_mf"


def test_percentis_ordenados():
    p = st.percentis(list(range(1, 101)))
    assert p[10] < p[50] < p[90]


def test_area_loader_km2_para_ha(tmp_path, monkeypatch):
    openpyxl = pytest.importorskip("openpyxl")  # noqa: F841
    import process_geography as pg
    (tmp_path / "ibge").mkdir()
    pd.DataFrame({"CD_MUN": ["3550308", "5107925"],
                  "AR_MUN_km2": ["1521,110", "9329,600"]}).to_excel(
        tmp_path / "ibge" / "areas_municipios.xlsx", index=False)
    monkeypatch.setattr(pg, "RAW_DIR", tmp_path)
    areas = pg._read_areas_ha()
    assert areas["3550308"] == pytest.approx(152111.0, abs=1)   # km² → ha
    assert areas["5107925"] == pytest.approx(932960.0, abs=1)


@pytest.mark.skipif(not DIM.exists(), reason="dim_municipio ainda não gerado")
def test_dim_municipio_integridade():
    df = pd.read_parquet(DIM)
    assert (df["cod_municipio"].astype(str).str.len() == 7).all()
    assert df["cod_municipio"].is_unique
    assert df["uf"].isna().sum() == 0
    # integridade referencial cod[:2] -> uf
    assert df.apply(lambda r: common.IBGE2UF.get(r["cod_municipio"][:2]) == r["uf"], axis=1).all()
    # áreas nunca zero (null é permitido)
    area = pd.to_numeric(df["area_municipal_ha"], errors="coerce")
    assert (area == 0).sum() == 0
