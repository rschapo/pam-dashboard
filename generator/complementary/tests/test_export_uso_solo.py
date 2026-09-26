import json

import pandas as pd
import pytest

import export_uso_solo as eu

ASSU, SORRISO, LAGOA_DOS_PATOS = "2400208", "5107925", "4300002"


def test_uso_solo_json_soma_os_grupos_e_deixa_fora_o_que_nao_e_municipio(tmp_path, monkeypatch):
    linhas = [
        (SORRISO, 2024, "formacao_florestal", 100.0), (SORRISO, 2024, "formacao_savanica", 50.0),
        (SORRISO, 2024, "area_umida", 10.0), (SORRISO, 2024, "agricultura", 600.0),
        (SORRISO, 2024, "area_nao_vegetada", 1.0),
        (SORRISO, 2024, None, 0.5),                      # classe fora do config (usina fotovoltaica)
        (SORRISO, 2024, "pastagem", 0.04),               # arredonda a zero: fica fora
        (SORRISO, 2023, "agricultura", 999.0),           # ano anterior
        (ASSU, 2024, "corpo_dagua", 20.0),
        (LAGOA_DOS_PATOS, 2024, "corpo_dagua", 1_000_000.0),
        (None, 2024, "pastagem", 0.1),                   # fragmento de borda sem município
    ]
    df = pd.DataFrame(linhas, columns=["cod_municipio", "ano", "grupo_analitico", "area_ha"])
    df["colecao"] = "10.1"
    (tmp_path / "municipality").mkdir()
    (tmp_path / "dimensions").mkdir()
    df.to_parquet(tmp_path / "municipality" / "mapbiomas_municipio.parquet", index=False)
    pd.DataFrame({"cod_municipio": [ASSU, SORRISO]}).to_parquet(
        tmp_path / "dimensions" / "dim_municipio.parquet", index=False)
    monkeypatch.setattr(eu, "PROCESSED_DIR", tmp_path)

    d = eu.build_uso_solo()

    assert (d["ano"], d["colecao"]) == (2024, "10.1")
    assert d["mun"] == {SORRISO: {"natural": 160.0, "agri": 600.0, "outros": 1.5}, ASSU: {"agua": 20.0}}
    assert d["fora_de_municipio"] == {
        LAGOA_DOS_PATOS: {"nome": "Lagoa dos Patos", "uf": "RS", "agua": 1_000_000.0}}


def test_uso_solo_json_real_cobre_os_municipios_sem_chave_vazia():
    p = eu.PUBLIC_DATA / "mapbiomas_mun.json"
    if not p.exists():
        pytest.skip("mapbiomas_mun.json ausente")
    d = json.loads(p.read_text(encoding="utf-8"))
    if "fora_de_municipio" not in d:
        pytest.skip("mapbiomas_mun.json ainda não saiu do export_uso_solo.py")
    dim = set(pd.read_parquet(eu.PROCESSED_DIR / "dimensions" / "dim_municipio.parquet")["cod_municipio"])

    assert set(d["mun"]) <= dim                      # nenhuma chave vazia ou código estranho
    # Os cinco que o MapBiomas grafa diferente do IBGE (São Luiz, Açu, Arês, Gracho
    # Cardoso, Barão de Monte Alto) agora têm dado.
    for cod in ("1400605", "2400208", "2401206", "2802601", "3105509"):
        assert sum(d["mun"][cod].values()) > 0, cod
    assert set(d["fora_de_municipio"]) == {"4300001", "4300002"}
    # Sem dado só Fernando de Noronha, que o MapBiomas não cobre, e Boa Esperança do
    # Norte, instalado em 2025, depois da malha da Coleção 10.1.
    assert dim - set(d["mun"]) == {"2605459", "5101837"}
