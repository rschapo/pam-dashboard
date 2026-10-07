import io
import json
import zipfile

import pandas as pd
import pytest

import process_demografia_pib as pdp

# Mato Grosso no SIDRA 5938, em mil R$: VAB por setor de 2021 (o último publicado)
# e PIB total de 2023. Os setores de 2021 somam o VAB total de 2021.
MT = {"agro": 79882439, "ind": 32177974, "serv": 73276756, "adm": 25007411,
      "total": 210344581, "impostos": 23045622}
PIB_MT_2023, POP_MT_2024 = 273008586, 3836399
POP_PIB_MT = 3658813   # a do per capita oficial de 2023 (Censo 2022, limites de 2023)

VARIAVEL = {
    "pib": "Produto Interno Bruto a preços correntes",
    "impostos": "Impostos, líquidos de subsídios, sobre produtos a preços correntes",
    "total": "Valor adicionado bruto a preços correntes total",
    "agro": "Valor adicionado bruto a preços correntes da agropecuária",
    "ind": "Valor adicionado bruto a preços correntes da indústria",
    "serv": ("Valor adicionado bruto a preços correntes dos serviços, exclusive administração, "
             "defesa, educação e saúde públicas e seguridade social"),
    "adm": ("Valor adicionado bruto a preços correntes da administração, defesa, educação e "
            "saúde públicas e seguridade social"),
}


def _sidra(linhas):
    """Resposta do /values: o cabeçalho e uma linha por (código, variável, valor)."""
    cab = {"D1C": "Unidade da Federação (Código)", "D2N": "Variável", "V": "Valor"}
    return [cab] + [{"D1C": cod, "D2N": var, "V": str(v)} for cod, var, v in linhas]


def _grava(pasta, nome, js):
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / nome).write_text(json.dumps(js, ensure_ascii=False), encoding="utf-8")


def test_campo_separa_os_servicos_da_administracao_publica_e_do_total():
    assert pdp._campo(VARIAVEL["serv"]) == "vab_servicos"
    assert pdp._campo(VARIAVEL["adm"]) == "vab_adm_publica"
    assert pdp._campo(VARIAVEL["total"]) == "vab_total"


def test_participacao_da_agropecuaria_divide_pelo_vab_total_do_mesmo_ano(tmp_path, monkeypatch):
    ibge = tmp_path / "ibge"
    _grava(ibge, "sidra_populacao_uf_2024.json", _sidra([("51", "População residente estimada", POP_MT_2024)]))
    _grava(ibge, "sidra_pibtotal_uf_2023.json", _sidra([("51", VARIAVEL["pib"], PIB_MT_2023)]))
    _grava(ibge, "sidra_vabsetorial_uf_2021.json", _sidra([("51", VARIAVEL[k], v) for k, v in MT.items()]))
    monkeypatch.setattr(pdp, "RAW_DIR", tmp_path)
    monkeypatch.setattr(pdp, "_populacao_do_pib", lambda ano: pd.DataFrame(
        {"cod_ibge": ["5107925", "5103403"], "populacao_pib": [POP_PIB_MT - 650_000.0, 650_000.0]}))

    df, ano_vab = pdp.build("3", 2023, 2024)

    mt = df.set_index("cod_uf").loc["51"]
    assert ano_vab == 2021
    assert (mt["vab_total"], mt["vab_adm_publica"]) == (MT["total"], MT["adm"])
    # Sobre o PIB de 2023 daria 29,26%, e sobre agro + indústria + serviços (sem a
    # administração pública), 43,11%.
    assert mt["pct_agro_no_vab"] == pytest.approx(37.98)
    assert "pct_agro_no_pib" not in df
    # O per capita usa a população do per capita oficial, somada dos municípios da UF,
    # e não a estimativa de 2024, que segue em populacao.
    assert (mt["populacao"], mt["populacao_pib"]) == (POP_MT_2024, POP_PIB_MT)
    assert mt["pib_per_capita"] == pytest.approx(PIB_MT_2023 * 1000 / POP_PIB_MT, abs=0.01)


def test_populacao_do_pib_sai_do_per_capita_oficial_da_base(tmp_path, monkeypatch):
    """PIB ÷ PIB per capita da base do PIB dos Municípios, só no ano pedido."""
    base = pd.DataFrame({
        "Ano": [2022, 2023],
        "Código do Município": [5107925, 5107925],
        "Produto Interno Bruto, \na preços correntes\n(R$ 1.000)": [9_000_000, 12_000_000],
        "Produto Interno Bruto per capita, \na preços correntes\n(R$ 1,00)": [90_000.0, 109_090.91],
    })
    xlsx = io.BytesIO()
    base.to_excel(xlsx, index=False, sheet_name="PIB dos Municípios")
    (tmp_path / "ibge").mkdir()
    with zipfile.ZipFile(tmp_path / "ibge" / "pib_municipios_base_2010_2023.zip", "w") as z:
        z.writestr("PIB dos Municípios - base de dados 2010-2023.xlsx", xlsx.getvalue())
    monkeypatch.setattr(pdp, "RAW_DIR", tmp_path)
    pdp._populacao_do_pib.cache_clear()

    pop = pdp._populacao_do_pib(2023)

    pdp._populacao_do_pib.cache_clear()
    assert pop.to_dict("records") == [{"cod_ibge": "5107925", "populacao_pib": 110000.0}]
