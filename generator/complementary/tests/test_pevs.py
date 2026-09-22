import pandas as pd

import process_pevs as pp


def test_grupos_carrega_config():
    g = pp._grupos()
    # silvicultura de eucalipto (área) mapeada
    assert ("AreaSilvicultura", "eucalipto") in g
    assert g[("Silvicultura", "carvão vegetal")] == "carvao_vegetal"


def test_build_descarta_total(tmp_path, monkeypatch):
    # cria um consolidado sintético e aponta o RAW_DIR para o tmp
    raw = tmp_path / "ibge" / "pevs"
    raw.mkdir(parents=True)
    df = pd.DataFrame([
        {"Cod_Municipio": "5107925", "Ano": 2020, "Tipo": "Silvicultura",
         "Categoria": "Carvão vegetal", "Unidade": "t", "q": "100", "v": "50", "a": ""},
        {"Cod_Municipio": "5107925", "Ano": 2020, "Tipo": "Silvicultura",
         "Categoria": "Total", "Unidade": "", "q": "999", "v": "999", "a": ""},
    ])
    df.to_csv(raw / "PEVS_municipios_completo.csv", sep=";", index=False, encoding="utf-8-sig")
    monkeypatch.setattr(pp, "RAW_DIR", tmp_path)
    out = pp.build()
    assert (out["produto"] == "Total").sum() == 0        # 'Total' descartado
    assert (out["produto"] == "Carvão vegetal").sum() == 1
    assert out.iloc[0]["grupo"] == "carvao_vegetal"
    assert out.iloc[0]["cod_municipio"] == "5107925"
