import json

import pandas as pd
import pytest

import export_car as ec

SORRISO, BOA_ESPERANCA = "5107925", "5101837"


def test_estrutura_fundiaria_junta_as_faixas_da_pequena_e_soma_os_denominadores(tmp_path, monkeypatch):
    pd.DataFrame({
        "cod_municipio": [SORRISO, BOA_ESPERANCA],
        "quantidade_imoveis": [10, 3], "quantidade_sem_modulo": [1, 3],
        "quantidade_ate_1_mf": [4, None], "quantidade_1_2_mf": [2, None], "quantidade_2_4_mf": [1, None],
        "quantidade_4_15_mf": [1, None], "quantidade_acima_15_mf": [1, None],
        "area_ate_4_mf_ha": [100.0, None], "area_4_15_mf_ha": [300.0, None],
        "area_acima_15_mf_ha": [1600.0, None],
    }).astype({c: "Int64" for c in ("quantidade_ate_1_mf", "quantidade_1_2_mf", "quantidade_2_4_mf",
                                     "quantidade_4_15_mf", "quantidade_acima_15_mf")}).to_parquet(
        tmp_path / "car_estrutura_fundiaria.parquet", index=False)
    monkeypatch.setattr(ec, "GEO", tmp_path)

    e = ec.estrutura_fundiaria()

    s = e.loc[SORRISO]
    assert (s["_npq"], s["_nmd"], s["_ngr"], s["_ncl"]) == (7, 1, 1, 9)   # o sem módulo fica fora
    assert (s["_apq"], s["_acl"]) == (100.0, 2000.0)
    assert e.loc[BOA_ESPERANCA].isna().all()      # sem classe: nada, e o município sai das razões


def test_estrutura_fundiaria_vazia_sem_a_tabela(tmp_path, monkeypatch):
    monkeypatch.setattr(ec, "GEO", tmp_path)
    assert ec.estrutura_fundiaria().empty


def test_car_json_real_recompoe_as_parcelas_do_brasil():
    """As razões do car.json, somadas no Brasil, dão as parcelas da tabela de origem."""
    p, t = ec.PUBLIC_DATA / "car.json", ec.GEO / "car_estrutura_fundiaria.parquet"
    if not p.exists() or not t.exists():
        pytest.skip("car.json ou car_estrutura_fundiaria ausentes")
    car = json.loads(p.read_text(encoding="utf-8"))
    if "pq_n" not in car["razoes"]:
        pytest.skip("car.json ainda sem a estrutura fundiária")
    e = pd.read_parquet(t)
    for tipo, fonte in (("n", "quantidade"), ("a", "area")):
        brasil = {}
        for c in ec.CLASSES_MF:
            r = car["razoes"][f"{c}_{tipo}"]
            num = sum(m.get(r["num"], 0) for m in car["mun"].values() if m.get(r["num"]) is not None)
            den = sum(m.get(r["den"], 0) for m in car["mun"].values() if m.get(r["num"]) is not None)
            brasil[c] = 100 * num / den
        assert sum(brasil.values()) == pytest.approx(100, abs=0.01)
        grandes = (e["quantidade_acima_15_mf"].sum() / (e["quantidade_imoveis"] - e["quantidade_sem_modulo"]).sum()
                   if fonte == "quantidade" else
                   e["area_acima_15_mf_ha"].sum() / e[["area_ate_4_mf_ha", "area_4_15_mf_ha",
                                                       "area_acima_15_mf_ha"]].sum().sum())
        assert brasil["gr"] == pytest.approx(100 * grandes, abs=0.01)   # áreas arredondadas a 1 ha
