import json

import pytest

import process_demografia_pib as pdp

# Mato Grosso no SIDRA 5938, em mil R$: VAB por setor de 2021 (o último publicado)
# e PIB total de 2023. Os setores de 2021 somam o VAB total de 2021.
MT = {"agro": 79882439, "ind": 32177974, "serv": 73276756, "adm": 25007411,
      "total": 210344581, "impostos": 23045622}
PIB_MT_2023, POP_MT_2024 = 273008586, 3836399

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

    df, ano_vab = pdp.build("3", 2023, 2024)

    mt = df.set_index("cod_uf").loc["51"]
    assert ano_vab == 2021
    assert (mt["vab_total"], mt["vab_adm_publica"]) == (MT["total"], MT["adm"])
    # Sobre o PIB de 2023 daria 29,26%, e sobre agro + indústria + serviços (sem a
    # administração pública), 43,11%.
    assert mt["pct_agro_no_vab"] == pytest.approx(37.98)
    assert "pct_agro_no_pib" not in df
