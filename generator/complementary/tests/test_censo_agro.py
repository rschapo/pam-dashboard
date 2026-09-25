import pandas as pd
import pytest

import download_censo_agro as dc
import process_censo_agro as pc

# Metadados da 6881 (utilização das terras) como a API v3 os devolve, com as
# categorias reduzidas às usadas aqui. Nas tabelas do Censo a unidade vem na
# variável; as categorias das classificações trazem unidade nula.
_TOTAL = {"id": 0, "nome": "Total", "unidade": None, "nivel": 0}
META_6881 = {
    "id": 6881,
    "nome": "Número de estabelecimentos agropecuários com área e Área dos estabelecimentos "
            "agropecuários, por tipologia, utilização das terras, condição do produtor em "
            "relação às terras, grupos de atividade econômica e origem da orientação técnica recebida",
    "URL": "https://sidra.ibge.gov.br/tabela/6881",
    "pesquisa": "Censo Agropecuário",
    "assunto": "Características dos estabelecimentos agropecuários ",
    "periodicidade": {"frequencia": "anual", "inicio": 2017, "fim": 2017},
    "nivelTerritorial": {"Administrativo": ["N1", "N2", "N8", "N9", "N6", "N3"],
                         "Especial": ["N132", "N133"], "IBGE": []},
    "variaveis": [
        {"id": 9587, "nome": "Número de estabelecimentos agropecuários com área",
         "unidade": "Unidades", "sumarizacao": ["nivelTerritorial"]},
        {"id": 184, "nome": "Área dos estabelecimentos agropecuários",
         "unidade": "Hectares", "sumarizacao": ["nivelTerritorial"]},
    ],
    "classificacoes": [
        {"id": 829, "nome": "Tipologia", "sumarizacao": {"status": True, "excecao": []},
         "categorias": [dict(_TOTAL, id=46302)]},
        {"id": 222, "nome": "Utilização das terras", "sumarizacao": {"status": True, "excecao": []},
         "categorias": [dict(_TOTAL, id=110087),
                        {"id": 113471, "nome": "Lavouras - temporárias", "unidade": None, "nivel": 1}]},
        {"id": 218, "nome": "Condição do produtor em relação às terras",
         "sumarizacao": {"status": True, "excecao": []}, "categorias": [dict(_TOTAL, id=46502)]},
        {"id": 12517, "nome": "Grupos de atividade econômica",
         "sumarizacao": {"status": True, "excecao": []}, "categorias": [dict(_TOTAL, id=113601)]},
        {"id": 12567, "nome": "Origem da orientação técnica recebida",
         "sumarizacao": {"status": True, "excecao": []}, "categorias": [dict(_TOTAL, id=41151)]},
    ],
}
CFG_USO = {"descricao": "Utilização das terras", "tabelas_candidatas": [6881],
           "metricas": {"estabelecimentos": "Número de estabelecimentos agropecuários com área",
                        "area": "Área dos estabelecimentos"},
           "classificacao_busca": ["utilização das terras"]}

# Resposta do /values para Sorriso (MT), conferida na API em 25/09/2026. A coluna
# MN se chama só "Unidade de Medida", sem "Nome".
CAB_VALUES = {
    "NC": "Nível Territorial (Código)", "NN": "Nível Territorial",
    "MC": "Unidade de Medida (Código)", "MN": "Unidade de Medida", "V": "Valor",
    "D1C": "Município (Código)", "D1N": "Município", "D2C": "Variável (Código)", "D2N": "Variável",
    "D3C": "Ano (Código)", "D3N": "Ano",
    "D4C": "Utilização das terras (Código)", "D4N": "Utilização das terras",
    "D5C": "Condição do produtor em relação às terras (Código)",
    "D5N": "Condição do produtor em relação às terras",
    "D6C": "Tipologia (Código)", "D6N": "Tipologia",
    "D7C": "Grupos de atividade econômica (Código)", "D7N": "Grupos de atividade econômica",
    "D8C": "Origem da orientação técnica recebida (Código)",
    "D8N": "Origem da orientação técnica recebida",
}
NUM_ESTAB = "Número de estabelecimentos agropecuários com área"
AREA_ESTAB = "Área dos estabelecimentos agropecuários"


def _linha_values(mc, mn, v, d2c, d2n, d4c, d4n):
    return {"NC": "6", "NN": "Município", "MC": mc, "MN": mn, "V": v,
            "D1C": "5107925", "D1N": "Sorriso (MT)", "D2C": d2c, "D2N": d2n,
            "D3C": "2017", "D3N": "2017", "D4C": d4c, "D4N": d4n,
            "D5C": "46502", "D5N": "Total", "D6C": "46302", "D6N": "Total",
            "D7C": "113601", "D7N": "Total", "D8C": "41151", "D8N": "Total"}


VALUES_6881_MT = [
    CAB_VALUES,
    _linha_values("1020", "Unidades", "828", "9587", NUM_ESTAB, "110087", "Total"),
    _linha_values("1020", "Unidades", "621", "9587", NUM_ESTAB, "113471", "Lavouras - temporárias"),
    _linha_values("1006", "Hectares", "827833", "184", AREA_ESTAB, "110087", "Total"),
    _linha_values("1006", "Hectares", "579102", "184", AREA_ESTAB, "113471", "Lavouras - temporárias"),
]


class _SidraGravado(dc.SidraClient):
    """Responde com os metadados e o /values acima, sem rede. Sem /values, falha se o
    coletor tentar baixar: um bruto já gravado não deve ser baixado de novo."""

    def __init__(self, values=None):
        super().__init__(pause=0)
        self.values = values

    def metadados(self, tabela):
        return META_6881

    def valores_municipais(self, tabela, variaveis, estado_cod, periodo, classif=None):
        if self.values is None:
            raise AssertionError("baixou de novo um bruto que já estava gravado")
        return self.values


@pytest.fixture
def pasta_uso(tmp_path, monkeypatch):
    monkeypatch.setattr(dc, "RAW_DIR", tmp_path)
    monkeypatch.setattr(dc, "ESTADOS_COD", [51])  # só MT
    return tmp_path / "censo_agro" / "land_use"


def test_coletor_grava_a_unidade_de_cada_linha(pasta_uso):
    """O coletor procurava a coluna da unidade com "Nome" no rótulo e a gravava
    vazia em todas as linhas."""
    dc.baixar_tema(_SidraGravado(VALUES_6881_MT), "land_use", CFG_USO, dry=False)
    d = pd.read_csv(pasta_uso / "land_use_6881_MT.csv", sep=";", dtype=str)
    assert list(zip(d["variavel"], d["unidade"])) == [
        (NUM_ESTAB, "Unidades"), (NUM_ESTAB, "Unidades"),
        (AREA_ESTAB, "Hectares"), (AREA_ESTAB, "Hectares"),
    ]


def test_coletor_completa_a_unidade_dos_brutos_ja_gravados(pasta_uso):
    """Os brutos gravados até 25/09/2026 têm a unidade vazia. Rodar o coletor de novo
    a preenche pela variável, com a unidade dos metadados, sem baixar nada e sem
    mexer no resto do arquivo (a linha sem valor também leva a unidade, como no /values)."""
    cab = "cod_municipio;ano_referencia;categoria;subcategoria;variavel;valor;unidade;fonte_tabela_sidra"
    pasta_uso.mkdir(parents=True)
    alvo = pasta_uso / "land_use_6881_MT.csv"
    alvo.write_text("\r\n".join([
        cab,
        f"5107925;2017;land_use;;{NUM_ESTAB};828.0;;6881",
        f"5107925;2017;land_use;;{AREA_ESTAB};827833.0;;6881",
        f"5107926;2017;land_use;;{AREA_ESTAB};;;6881",
    ]) + "\r\n", encoding="utf-8", newline="")
    dc.baixar_tema(_SidraGravado(), "land_use", CFG_USO, dry=False)
    assert alvo.read_text(encoding="utf-8").splitlines() == [
        cab,
        f"5107925;2017;land_use;;{NUM_ESTAB};828.0;Unidades;6881",
        f"5107925;2017;land_use;;{AREA_ESTAB};827833.0;Hectares;6881",
        f"5107926;2017;land_use;;{AREA_ESTAB};;Hectares;6881",
    ]


def test_tabelas_reais_trazem_a_unidade():
    """Toda linha das tabelas do Censo tem unidade, uma só por variável. O coletor
    gravava a unidade vazia em todas."""
    tabelas = [pc.PROCESSED_DIR / "municipality" / f"censo_agro_{t}.parquet" for t in pc.TEMAS]
    if not all(p.exists() for p in tabelas):
        pytest.skip("tabelas do Censo ausentes")
    for p in tabelas:
        df = pd.read_parquet(p, columns=["variavel", "unidade"])
        assert (df["unidade"].fillna("") != "").all(), p.name
        assert (df.groupby("variavel")["unidade"].nunique() == 1).all(), p.name
    maq = pd.read_parquet(tabelas[pc.TEMAS.index("machinery")])
    assert maq.groupby("variavel")["unidade"].first().to_dict() == {
        "Número de estabelecimentos agropecuários com tratores": "Unidades",
        "Número de tratores existentes nos estabelecimentos agropecuários": "Unidades",
    }


NUM_6778 = "Número de estabelecimentos agropecuários"


def _area_groups(*linhas):
    """Linhas da area_groups como o processamento as lê: (município, subcategoria, variável, valor)."""
    return pd.DataFrame([{"cod_municipio": m, "ano_referencia": 2017, "categoria": "area_groups",
                          "subcategoria": s, "variavel": var, "valor": v, "unidade": "Unidades",
                          "fonte_tabela_sidra": 6778} for m, s, var, v in linhas])


def test_resumo_conta_so_o_total_dos_estabelecimentos():
    """A area_groups traz o Total e as faixas de área da mesma variável; o resumo somava
    tudo e contava cada estabelecimento duas vezes."""
    s = pc._summary({"area_groups": _area_groups(
        ("1200013", "Total", NUM_6778, "1462"),
        ("1200013", "De 1 a menos de 2 ha", NUM_6778, "17"),
        ("1200013", "De 10 a menos de 20 ha", NUM_6778, "1445"),
    )}).set_index("cod_municipio")
    assert s.loc["1200013", "numero_estabelecimentos"] == 1462


def test_resumo_nao_soma_a_area_na_contagem():
    # "Área dos estabelecimentos" também contém "estabelecimentos"
    s = pc._summary({"area_groups": _area_groups(
        ("5107925", "Total", NUM_6778, "828"),
        ("5107925", "Total", AREA_ESTAB, "827833"),
        ("5107925", "De 1 a menos de 2 ha", AREA_ESTAB, "12"),
    )}).set_index("cod_municipio")
    assert s.loc["5107925", "numero_estabelecimentos"] == 828
    assert s.loc["5107925", "area_estabelecimentos_ha"] == 827833


def test_resumo_sem_rotulo_fica_nulo_e_nao_dobra():
    """Bruto sem subcategoria (baixado antes de o coletor gravá-la) não separa o Total
    das faixas: o município fica no resumo, com o valor nulo."""
    s = pc._summary({"area_groups": _area_groups(
        ("1200013", None, NUM_6778, "1462"),
        ("1200013", None, NUM_6778, "1462"),
    )}).set_index("cod_municipio")
    assert pd.isna(s.loc["1200013", "numero_estabelecimentos"])


def test_resumo_real_conta_os_estabelecimentos_do_censo_2017():
    """No resumo gerado, um município por linha, e o Brasil soma o total de
    estabelecimentos agropecuários publicado pelo IBGE para o Censo 2017. A área, que
    vinha nula, fecha com a do Brasil a menos dos poucos municípios em que o IBGE a suprime."""
    p = pc.PROCESSED_DIR / "municipality" / "censo_agro_municipio_summary.parquet"
    if not p.exists():
        pytest.skip("resumo do Censo ausente")
    s = pd.read_parquet(p)
    assert s["cod_municipio"].is_unique
    assert s["numero_estabelecimentos"].sum() == 5_073_324
    area = s["area_estabelecimentos_ha"]
    assert area.notna().mean() > 0.99
    assert 351_289_816 * 0.999 < area.sum() < 351_289_816


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
