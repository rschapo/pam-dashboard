import json

import pandas as pd
import pytest

import export_econ as ee

SORRISO, BOA_ESPERANCA = "5107925", "5101837"
COLUNAS = ["populacao", "pib_total", "vab_agropecuaria", "vab_industria", "vab_servicos",
           "vab_adm_publica", "vab_total", "impostos_liquidos"]


def _tabela(chave, linhas):
    df = pd.DataFrame([{chave: cod, **dict(zip(COLUNAS, v))} for cod, v in linhas])
    df["ano_ref"], df["ano_ref_vab"] = 2023, 2021
    return df


def test_econ_json_leva_os_componentes_e_o_vab_total_como_denominador_oculto(tmp_path, monkeypatch):
    (tmp_path / "municipality").mkdir()
    (tmp_path / "state").mkdir()
    _tabela("cod_ibge", [
        (SORRISO, (110_000, 12_000_000.0, 5_000_000.0, 1_000_000.0, 3_000_000.0,
                   500_000.0, 9_500_000.0, 2_500_000.0)),
        (BOA_ESPERANCA, (None,) * len(COLUNAS)),
    ]).to_parquet(tmp_path / "municipality" / "demografia_pib.parquet", index=False)
    _tabela("cod_uf", [
        ("51", (3_836_399, 273_008_586.0, 79_882_439.0, 32_177_974.0, 73_276_756.0,
                25_007_411.0, 210_344_581.0, 23_045_622.0)),
    ]).to_parquet(tmp_path / "state" / "demografia_pib.parquet", index=False)
    monkeypatch.setattr(ee, "PROCESSED_DIR", tmp_path)

    e = ee.build_econ()

    assert (e["ano_pib"], e["ano_vab"]) == (2023, 2021)
    assert e["mun"][SORRISO] == {"pop": 110000, "pib": 12000000, "agro": 5000000,
                                 "ind": 1000000, "serv": 3000000, "_vab": 9500000}
    assert BOA_ESPERANCA not in e["mun"]      # sem dado: fica fora, e o front mostra "—"
    assert e["uf"]["MT"]["_vab"] == 210344581


def test_econ_json_real_recompoe_a_participacao_do_mt_no_mesmo_ano():
    """O que o front recompõe (agro ÷ _vab) fica entre 0 e 100% e bate com a UF."""
    p = ee.PUBLIC_DATA / "econ.json"
    if not p.exists():
        pytest.skip("econ.json ausente")
    e = json.loads(p.read_text(encoding="utf-8"))
    if not any("_vab" in m for m in e["mun"].values()):
        pytest.skip("econ.json ainda sem o VAB total")
    # Com VAB total negativo a participação sai negativa, e é assim que o IBGE a
    # publica (Cachoeira Dourada, GO, em 2021: −41,90%, com a indústria negativa).
    fora = [c for c, m in e["mun"].items() if m.get("_vab", 0) > 0 and not 0 <= m.get("agro", 0) <= m["_vab"]]
    assert fora == []
    mt = [m for c, m in e["mun"].items() if c.startswith("51") and m.get("agro") is not None]
    pct_mt = 100 * sum(m["agro"] for m in mt) / sum(m["_vab"] for m in mt)
    assert pct_mt == pytest.approx(100 * e["uf"]["MT"]["agro"] / e["uf"]["MT"]["_vab"], abs=0.01)
    assert pct_mt == pytest.approx(37.98, abs=0.01)   # 79.882.439 ÷ 210.344.581, SIDRA 5938
