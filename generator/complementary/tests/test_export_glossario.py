import json
import os
from datetime import datetime

import pytest

import export_glossario as eg


def _grava(pasta, nome, obj):
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / nome).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def base(tmp_path, monkeypatch):
    """public/data, manifestos e brutos mínimos num diretório temporário."""
    dados, man, raw = tmp_path / "data", tmp_path / "manifests", tmp_path / "raw"
    _grava(dados, "pkg.json", {"anos": [2004, 2025], "permanentes": ["Café (em grão) Total"],
                               "temporarias": ["Soja (em grão)", "Mandioca"],
                               "colheitadeiras": ["Soja (em grão)"], "tratores": ["Mandioca"]})
    _grava(dados, "ppm.json", {"anos": [2004, 2025], "rebanho_categorias": ["Bovino"],
                               "producao_categorias": ["Leite"]})
    carvao, eucalipto = "1.1 - Carvão vegetal", "1.1.3 - Carvão vegetal de eucalipto"
    _grava(dados, "pevs.json", {
        "anos": [2004, 2013, 2025], "sep": "||",
        "categorias_por_tipo": {"Silvicultura": [carvao, eucalipto]},
        "nivel_categoria": {f"Silvicultura||{carvao}": "produto", f"Silvicultura||{eucalipto}": "especie"},
        "unidades": {carvao: "t", eucalipto: "t"},
        "periodo_categoria": {f"Silvicultura||{eucalipto}": [2013, 2025]},
        "notas": {"Silvicultura": ["Em 2025 o IBGE passou a separar a teca."]}})
    _grava(dados, "econ.json", {"ano_pib": 2023, "ano_vab": 2021,
                                "ref_pop": "Censo 2022, como no per capita oficial do IBGE"})
    _grava(dados, "car.json", {"ressalvas": {
        "notas": {"app": ["PE: abaixo dos vizinhos, sem confirmação."]},
        "estrutura": {"campos": ["pq_n"], "nota": "Conta inscrições no CAR, não propriedades."},
        "area_omitida": 155}})
    _grava(man, "raw_demografia_pib.json", {"extraction_date": "2026-10-06T23:20:00-03:00"})
    # PAM, PPM e PEVS não têm manifesto: a data é a do consolidado municipal.
    arq = raw / "ibge" / "pam" / "PAM_municipios_completo.csv"
    arq.parent.mkdir(parents=True)
    arq.write_text("cod;valor\n", encoding="utf-8")
    t = datetime(2026, 9, 21, 12).timestamp()
    os.utime(arq, (t, t))
    monkeypatch.setattr(eg, "PUBLIC_DATA", dados)
    monkeypatch.setattr(eg, "MANIFEST_DIR", man)
    monkeypatch.setattr(eg, "RAW_DIR", raw)
    return dados


def test_fontes_tiram_periodo_e_data_do_download_dos_dados(base):
    fontes = {f["aba"]: f for f in eg.build_glossario()["fontes"]}

    assert fontes["Agrícola"]["periodo"] == "2004–2025"
    assert fontes["Agrícola"]["baixado_em"] == "set/2026"
    eco = fontes["Economia"]
    assert eco["periodo"] == "PIB 2023; VAB por setor 2021"
    assert eco["nota"] == "população do per capita: Censo 2022, como no per capita oficial do IBGE"
    assert eco["baixado_em"] == "out/2026"
    # Sem consolidado nem manifesto, a data fica de fora, em vez de sair como null.
    assert "baixado_em" not in fontes["Pecuária"]
    assert "baixado_em" not in fontes["CAR"]


def test_listas_de_culturas_e_categorias_saem_dos_json_do_painel(base):
    g = eg.build_glossario()

    assert g["culturas"] == {"permanentes": ["Café (em grão) Total"],
                             "temporarias": ["Soja (em grão)", "Mandioca"],
                             "colheitadeiras": ["Soja (em grão)"], "tratores": ["Mandioca"]}
    assert g["pecuaria"] == {"rebanho": ["Bovino"], "producao": ["Leite"]}
    assert g["pevs"]["anos"] == [2004, 2025]
    assert g["pevs"]["tipos"]["Silvicultura"] == [
        {"categoria": "1.1 - Carvão vegetal", "nivel": "produto", "unidade": "t", "periodo": None},
        {"categoria": "1.1.3 - Carvão vegetal de eucalipto", "nivel": "especie", "unidade": "t",
         "periodo": [2013, 2025]}]
    assert g["pevs"]["notas"]["Silvicultura"] == ["Em 2025 o IBGE passou a separar a teca."]


def test_car_leva_as_ressalvas_por_camada_e_a_da_estrutura(base):
    assert eg.build_glossario()["car"] == {
        "notas": {"app": ["PE: abaixo dos vizinhos, sem confirmação."]},
        "estrutura": "Conta inscrições no CAR, não propriedades.",
        "area_omitida": 155}


def test_sem_os_json_do_painel_o_glossario_sai_sem_listas(tmp_path, monkeypatch):
    monkeypatch.setattr(eg, "PUBLIC_DATA", tmp_path / "vazio")
    monkeypatch.setattr(eg, "MANIFEST_DIR", tmp_path / "vazio")
    monkeypatch.setattr(eg, "RAW_DIR", tmp_path / "vazio")

    g = eg.build_glossario()

    assert len(g["fontes"]) == 11 and g["fontes"][0]["periodo"] == "—"
    assert all("baixado_em" not in f for f in g["fontes"])
    assert g["culturas"]["temporarias"] == [] and g["pevs"] == {"anos": [], "tipos": {}, "notas": {}}


def test_glossario_real_tem_os_grupos_de_maquina_dentro_das_temporarias():
    """O glossário diz que Colheitadeiras e Tratores repartem as temporárias."""
    p = eg.PUBLIC_DATA / "glossario.json"
    if not p.exists():
        pytest.skip("glossario.json ainda não gerado")
    c = json.loads(p.read_text(encoding="utf-8"))["culturas"]
    col, tra, tem = set(c["colheitadeiras"]), set(c["tratores"]), set(c["temporarias"])
    assert col and tra and not col & tra
    assert col | tra == tem
    assert not tem & set(c["permanentes"])
