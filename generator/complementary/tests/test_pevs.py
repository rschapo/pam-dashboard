import pandas as pd
import pytest

import process_pevs as pp


def _consolidado(tmp_path, monkeypatch, linhas):
    """Grava um consolidado sintético e aponta o RAW_DIR para ele."""
    raw = tmp_path / "ibge" / "pevs"
    raw.mkdir(parents=True)
    pd.DataFrame(linhas).to_csv(raw / "PEVS_municipios_completo.csv", sep=";",
                                index=False, encoding="utf-8-sig")
    monkeypatch.setattr(pp, "RAW_DIR", tmp_path)


def _linha(ano, tipo, cod, categoria, q="", v="", a=""):
    return {"Cod_Municipio": "5107925", "Ano": ano, "Tipo": tipo, "Cod_Categoria": cod,
            "Categoria": categoria, "Unidade": "", "q": q, "v": v, "a": a}


def test_grupos_casam_pelo_codigo_do_sidra():
    g = pp._grupos()
    assert g[("Silvicultura", "3455")] == "carvao_vegetal"            # 1.1 - Carvão vegetal
    assert g[("Extracao", "3405")] == "extracao_nao_madeireira"        # 1.6 - Castanha-do-pará
    assert g[("Extracao", "3435")] == "extracao_madeireira"            # 7.3 - Madeira em tora
    assert g[("AreaSilvicultura", "39326")] == "eucalipto"
    # agregado, espécie e contagem repetem produção de outra linha: sem grupo
    assert g[("Silvicultura", "3457")] is None                         # 1.3 = 1.3.1 + 1.3.2
    assert g[("Silvicultura", "33247")] is None                        # carvão de eucalipto
    assert g[("Extracao", "3402")] is None                             # 1 - Alimentícios
    assert g[("Extracao", "3449")] is None                             # árvores abatidas


def test_grupos_recusa_agregado_com_grupo(tmp_path, monkeypatch):
    (tmp_path / "forestry_groups.csv").write_text(
        "tipo_atividade;cod_categoria;produto;nivel;grupo;observacao\n"
        "Silvicultura;3457;1.3 - Madeira em tora;agregado;madeira_tora_outros_fins;\n",
        encoding="utf-8")
    monkeypatch.setattr(pp, "CONFIG_DIR", tmp_path)
    with pytest.raises(ValueError, match="1.3 - Madeira em tora"):
        pp._grupos()


def test_build_descarta_total(tmp_path, monkeypatch):
    _consolidado(tmp_path, monkeypatch, [
        _linha(2020, "Silvicultura", "3455", "1.1 - Carvão vegetal", "100", "50"),
        _linha(2020, "Silvicultura", "0", "Total", v="999"),
    ])
    out = pp.build()
    assert out["produto"].tolist() == ["1.1 - Carvão vegetal"]        # 'Total' descartado
    assert out.iloc[0]["grupo"] == "carvao_vegetal"
    assert out.iloc[0]["cod_municipio"] == "5107925"


def test_build_casa_pelo_codigo_com_rotulo_renumerado(tmp_path, monkeypatch):
    # Em 2025 o IBGE renumerou o carvão de eucalipto (1.1.1 -> 1.1.3) e passou a
    # omitir o " - " nos produtos novos; o código do SIDRA não mudou.
    _consolidado(tmp_path, monkeypatch, [
        _linha(2024, "Silvicultura", "3455", "1.1 - Carvão vegetal", "100", "50"),
        _linha(2024, "Silvicultura", "33247", "1.1.1 - Carvão vegetal de eucalipto", "100", "50"),
        _linha(2025, "Silvicultura", "3455", "1.1 - Carvão vegetal", "120", "60"),
        _linha(2025, "Silvicultura", "33247", "1.1.3 - Carvão vegetal de eucalipto", "120", "60"),
        _linha(2025, "Silvicultura", "3457", "1.3 - Madeira em tora", "80", "40"),
        _linha(2025, "Extracao", "83410", "1.2 Baru ou Cumaru (amêndoa)", "3", "9"),
        _linha(2025, "AreaSilvicultura", "83439", "Teca", a="40"),
    ])
    g = pp.build().set_index(["ano", "produto"])["grupo"]
    assert g[(2024, "1.1 - Carvão vegetal")] == g[(2025, "1.1 - Carvão vegetal")] == "carvao_vegetal"
    assert pd.isna(g[(2024, "1.1.3 - Carvão vegetal de eucalipto")])  # rótulo mais recente, sem grupo
    assert pd.isna(g[(2025, "1.3 - Madeira em tora")])
    assert g[(2025, "1.2 - Baru ou Cumaru (amêndoa)")] == "extracao_nao_madeireira"
    assert g[(2025, "Teca")] == "outras_especies"


def test_consolidado_real_soma_por_grupo_fecha_com_o_total():
    """Todo código do consolidado tem linha na config, e somar por grupo não repete
    produção: o valor (área, na 5930) das linhas com grupo fecha com o Total do IBGE."""
    if not (pp.RAW_DIR / "ibge" / "pevs" / "PEVS_municipios_completo.csv").exists():
        pytest.skip("consolidado PEVS ausente (os brutos ficam fora do repositório)")
    df = pp._read_pevs()
    g = pp._grupos()
    chave = pd.Series(list(zip(df["Tipo"], df["Cod_Categoria"].astype(str))), index=df.index)
    total = df["Cod_Categoria"].astype(str) == "0"
    faltam = sorted(set(chave[~total]) - set(g))
    assert not faltam, f"códigos sem linha em forestry_groups.csv: {faltam}"
    com_grupo = pd.Series([g.get(k) for k in chave], index=df.index).notna()
    for tipo, col in (("Silvicultura", "v"), ("Extracao", "v"), ("AreaSilvicultura", "a")):
        x = pd.to_numeric(df[col], errors="coerce").where(df["Tipo"] == tipo)
        assert x[com_grupo].sum() == pytest.approx(x[total].sum(), rel=1e-4), tipo
