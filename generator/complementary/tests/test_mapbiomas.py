import json

import pandas as pd

import process_mapbiomas as pm

REF = [("1400605", "São Luiz do Anauá", "RR"), ("2400208", "Assú", "RN"), ("2401206", "Arez", "RN"),
       ("2802601", "Graccho Cardoso", "SE"), ("3105509", "Barão do Monte Alto", "MG"),
       ("1503606", "Itaituba", "PA")]


def test_grafias_do_mapbiomas_casam_com_o_ibge_e_as_lagoas_ganham_codigo_proprio(tmp_path, monkeypatch):
    (tmp_path / "ibge").mkdir()
    pd.DataFrame(REF, columns=["cod_ibge", "nome_municipio", "sigla_uf"]).to_csv(
        tmp_path / "ibge" / "municipios.csv", sep=";", index=False)
    monkeypatch.setattr(pm, "RAW_DIR", tmp_path)
    raw = pd.DataFrame({
        "municipality": ["São Luiz", "Açu", "Arês", "Gracho Cardoso", "Barão de Monte Alto",
                         "Lagoa dos Patos", "Lagoa Mirim", "Itaituba", "Itaituba"],
        "state_acronym": ["RR", "RN", "RN", "SE", "MG", "RS", "RS", "PA", "AM"],
    })

    lookup, chaves = pm._resolver_cod_ibge(raw, "municipality", "state_acronym")

    # O último é um fragmento de Itaituba rotulado com a UF vizinha: sem palpite, fica sem código.
    assert [lookup.get(k) for k in chaves] == ["1400605", "2400208", "2401206", "2802601", "3105509",
                                               "4300002", "4300001", "1503606", None]


def test_data_download_vem_do_manifesto_do_bruto_e_nao_do_dia_do_processamento(tmp_path, monkeypatch):
    monkeypatch.setattr(pm, "MANIFEST_DIR", tmp_path)
    monkeypatch.setattr(pm, "today_iso", lambda: "2026-09-26")
    assert pm._data_download() == "2026-09-26"          # sem manifesto, a data do dia

    (tmp_path / "raw_mapbiomas.json").write_text(json.dumps({"extraction_date": "2026-08-08"}),
                                                 encoding="utf-8")
    assert pm._data_download() == "2026-08-08"
