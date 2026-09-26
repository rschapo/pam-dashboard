import pandas as pd
import pytest

import process_car_estrutura as pce

SORRISO, SINOP = "5107925", "5107909"
MF = pd.Series({SORRISO: 90.0, SINOP: 100.0})


def test_classe_segue_os_limites_da_lei_e_das_faixas_analiticas():
    s = pd.Series([0.0, 1.0, 2.0, 4.0, 4.01, 15.0, 15.01, None])
    assert pce.classe(s).tolist()[:7] == ["ate_4_mf"] * 4 + ["mais_4_ate_15_mf"] * 2 + ["mais_15_mf"]
    assert pd.isna(pce.classe(s).iloc[7])
    assert pce.classe(s, pce.FAIXAS_MF_ANALITICA).tolist()[:4] == [
        "ate_1_mf", "ate_1_mf", "mais_1_ate_2_mf", "mais_2_ate_4_mf"]


def test_imoveis_uf_tira_cancelados_e_repetidos_e_usa_o_municipio_principal(tmp_path, monkeypatch):
    pd.DataFrame(
        [("a", SORRISO, 180.0, 2.0, "ativo"),       # a maior parte da área está em Sinop
         ("b", SORRISO, 450.0, 5.0, "pendente"),
         ("b", SORRISO, 450.0, 5.0, "pendente"),    # código repetido
         ("c", SORRISO, 90.0, 1.0, "cancelado"),
         ("d", SORRISO, 0.0, 0.0, "ativo")],         # sem interseção com a malha e sem área
        columns=["id_car_hash", "cod_municipio_declarado", "area_geometrica_ha",
                 "modulos_fiscais_declarado", "situacao_car_padronizada"],
    ).to_parquet(tmp_path / "car_imoveis_validos_MT.parquet", index=False)
    pd.DataFrame([("a", SINOP, True), ("a", SORRISO, False), ("b", SORRISO, True), ("c", SORRISO, True)],
                 columns=["id_car_hash", "cod_municipio", "municipio_principal"],
                 ).to_parquet(tmp_path / "car_imovel_municipio_intersection_MT.parquet", index=False)
    monkeypatch.setattr(pce, "GEO", tmp_path)

    v, cancelados = pce.imoveis_uf("MT", MF)

    v = v.set_index("id_car_hash")
    assert (sorted(v.index), cancelados) == (["a", "b", "d"], 1)
    assert v.at["a", "cod_municipio"] == SINOP and v.at["d", "cod_municipio"] == SORRISO
    assert v.at["a", "modulos_fiscais"] == pytest.approx(1.8)          # 180 ha ÷ 100 ha de Sinop
    assert (v.at["a", "classe"], v.at["b", "classe"]) == ("ate_4_mf", "mais_4_ate_15_mf")
    assert pd.isna(v.at["d", "classe"])                                  # área zero: sem classe


def test_resumir_da_percentuais_por_imovel_e_por_area_e_nulo_sem_classe():
    v = pce.classificar(pd.DataFrame({
        "cod_municipio": [SORRISO, SORRISO, SORRISO, "5101837"],     # o último não tem módulo fiscal
        "area_geometrica_ha": [45.0, 135.0, 9000.0, 50.0],
        "modulos_fiscais_declarado": [0.5, 1.5, 100.0, 1.0]}), MF)
    r = pce.resumir(v).set_index("cod_municipio")
    s = r.loc[SORRISO]
    assert (s["quantidade_imoveis"], s["quantidade_ate_1_mf"], s["quantidade_1_2_mf"],
            s["quantidade_2_4_mf"], s["quantidade_4_15_mf"], s["quantidade_acima_15_mf"]) == (3, 1, 1, 0, 0, 1)
    assert (s["percentual_imoveis_ate_4_mf"], s["percentual_imoveis_4_15_mf"],
            s["percentual_imoveis_acima_15_mf"]) == (66.67, 0.0, 33.33)
    assert (s["percentual_area_ate_4_mf"], s["percentual_area_acima_15_mf"]) == (1.96, 98.04)
    assert s["modulos_fiscais_mediana"] == 1.5
    b = r.loc["5101837"]
    assert (b["quantidade_imoveis"], b["quantidade_sem_modulo"]) == (1, 1)
    assert pd.isna(b["percentual_imoveis_ate_4_mf"]) and pd.isna(b["quantidade_4_15_mf"])  # nulo, nunca zero


def test_concordancia_so_conta_imoveis_com_as_duas_classes():
    v = pd.DataFrame({"classe": ["ate_4_mf", "mais_15_mf", None, "ate_4_mf"],
                      "classe_sicar": ["ate_4_mf", "mais_4_ate_15_mf", "ate_4_mf", None]})
    assert pce.concordancia(v) == 50.0


def test_estrutura_real_fecha_por_municipio():
    p = pce.GEO / "car_estrutura_fundiaria.parquet"
    if not p.exists():
        pytest.skip("car_estrutura_fundiaria ainda não gerada")
    d = pd.read_parquet(p)
    faixas = ["quantidade_ate_1_mf", "quantidade_1_2_mf", "quantidade_2_4_mf",
              "quantidade_4_15_mf", "quantidade_acima_15_mf"]
    assert (d[faixas].sum(axis=1) + d["quantidade_sem_modulo"] == d["quantidade_imoveis"]).all()
    for tipo in ("imoveis", "area"):
        cols = [f"percentual_{tipo}_{s}" for s in ("ate_4_mf", "4_15_mf", "acima_15_mf")]
        com = d[cols].notna().all(axis=1)
        assert ((d.loc[com, cols].sum(axis=1) - 100).abs() <= 0.05).all()
