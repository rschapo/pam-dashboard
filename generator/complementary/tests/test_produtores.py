import csv
import json
import re

import pandas as pd
import pytest

import process_produtores as pp
import receita_common as rc


def test_tabela_de_cnae_cobre_as_subclasses_01_e_02_com_atividade_conhecida():
    with open(pp.CNAE_CSV, encoding="utf-8-sig", newline="") as fh:
        linhas = list(csv.DictReader(fh, delimiter=";"))
    cnaes = [r["cnae"] for r in linhas]
    assert len(cnaes) == len(set(cnaes)) == 100          # as 100 subclasses da tabela `cnaes` da Receita
    assert all(re.fullmatch(r"0[12]\d{5}", c) for c in cnaes)
    assert {r["atividade"] for r in linhas} == set(pp.ATIVIDADES)
    m = pp.mapa_cnae()
    assert (m["0113000"], m["0131800"], m["0133404"], m["0134200"]) == ("cana", "citros", "citros", "cafe")
    assert (m["0115600"], m["0121101"], m["0151202"], m["0161003"], m["0210101"]) == \
        ("graos", "hf", "bovinos", "servicos", "florestal")


def test_cnae_fora_da_tabela_para_a_rodada():
    with pytest.raises(SystemExit):
        pp.classificar_atividade(pd.Series(["0113000", "0199999"]), pp.mapa_cnae())


def test_natureza():
    assert [rc.tipo_natureza(x) for x in ("4120", "2062", "2143", "3999", None)] == \
        ["PF", "PJ", "PJ", "outra", "outra"]


def test_exclusoes_saem_antes_de_contar(tmp_path):
    lista = tmp_path / "exclusoes_lgpd.csv"
    assert pp.carregar_exclusoes(lista) == (set(), set())          # cria só o cabeçalho
    assert lista.read_text(encoding="utf-8").strip() == "cnpj;data;canal;responsavel"
    lista.write_text("cnpj;data;canal;responsavel\n11.111.111/0001-01;2026-10-21;e-mail;teste\n"
                     "22222222;2026-10-21;telefone;teste\n", encoding="utf-8")
    c14, r8 = pp.carregar_exclusoes(lista)
    df = pd.DataFrame({"cnpj": ["11111111000101", "11111111000282", "22222222000101", "33333333000101"],
                       "cod_municipio": ["3550308"] * 4, "atividade": ["cana"] * 4, "tipo": ["PF"] * 4,
                       "data_inicio": ["20250101", "20100101", "20250101", "20250101"]})
    fica, n = pp.aplicar_exclusoes(df, c14, r8)
    assert n == 2 and fica["cnpj"].tolist() == ["11111111000282", "33333333000101"]
    ag = pp.agregar(fica, "20241011")
    assert ag[["ativos", "novos_24m"]].values.tolist() == [[2, 1]]


def test_supressao_desligada_por_padrao():
    ag = pd.DataFrame({"cod_municipio": ["3550308", "3550308"], "atividade": ["cana", "cafe"],
                       "tipo": ["PF", "PJ"], "ativos": [1, 7], "novos_24m": [0, 2]})
    assert pp.json_mun(ag) == {"3550308": {"cana|PF": [1, 0], "cafe|PJ": [7, 2]}}
    assert pp.json_mun(ag, 3) == {"3550308": {"cana|PF": [None, 0], "cafe|PJ": [7, None]}}


def _publico():
    p = pp.PUBLIC_DATA / "produtores_mun.json"
    if not p.exists():
        pytest.skip("produtores_mun.json ainda não gerado (process_produtores.py)")
    return json.loads(p.read_text(encoding="utf-8"))


def test_json_publico_so_tem_codigos_ibge_e_numeros():
    d = _publico()
    chaves = {f"{a}|{t}" for a in d["atividades"] for t in d["tipos"]}
    for cod, o in d["mun"].items():
        assert re.fullmatch(r"[1-5]\d{6}", cod)
        assert set(o) <= chaves
        for v in o.values():
            assert len(v) == 2 and all(x is None or (isinstance(x, int) and x >= 0) for x in v)
    assert set(d) == {"fonte", "periodo_rfb", "data_ref", "corte_24m", "gerado_em", "atividades",
                      "tipos", "cautelas", "suprimido_abaixo", "comparacao_censo_uf", "mun"}


def test_json_publico_bate_com_o_agregado_processado():
    d = _publico()
    ag = pd.read_parquet(pp.PROCESSED_DIR / "municipality" / "produtores_municipio.parquet")
    assert d["periodo_rfb"] == ag["periodo_rfb"].iloc[0]
    if d["suprimido_abaixo"]:
        pytest.skip("JSON com supressão: a soma não fecha por construção")
    tot = sum(v[0] for o in d["mun"].values() for v in o.values())
    assert tot == ag["ativos"].sum()
    por_uf = ag.assign(uf=ag["cod_municipio"].str[:2]).groupby("uf")["ativos"].sum()
    from common import UF2IBGE
    assert all(d["comparacao_censo_uf"][uf]["cadastros"] == por_uf.get(UF2IBGE[uf], 0)
               for uf in d["comparacao_censo_uf"])


def test_agregado_e_a_soma_da_base_local():
    cache = rc.pf_cache_existente()
    d = _publico()
    base_p = cache / f"produtores_base_{d['periodo_rfb']}.parquet" if cache else None
    if not base_p or not base_p.exists():
        pytest.skip("base local de produtores ausente nesta máquina (cache fora do OneDrive)")
    base = pd.read_parquet(base_p, columns=["cnpj", "cod_municipio", "atividade", "tipo", "data_inicio"])
    corte = d["corte_24m"].replace("-", "")
    recont = pp.agregar(base, corte).set_index(["cod_municipio", "atividade", "tipo"])[["ativos", "novos_24m"]]
    ag = (pd.read_parquet(pp.PROCESSED_DIR / "municipality" / "produtores_municipio.parquet")
            .set_index(["cod_municipio", "atividade", "tipo"])[["ativos", "novos_24m"]])
    pd.testing.assert_frame_equal(recont.sort_index(), ag.sort_index(), check_dtype=False)
    # a lista de exclusão foi aplicada: nenhum excluído ficou na base local
    c14, r8 = pp.carregar_exclusoes(cache / "exclusoes_lgpd.csv")
    assert not (base["cnpj"].isin(c14) | base["cnpj"].str[:8].isin(r8)).any()


def test_cache_de_dado_pessoal_recusa_projeto_e_onedrive(tmp_path, monkeypatch):
    monkeypatch.setenv("PAM_CACHE_PF", str(rc.PROJECT_ROOT / "data" / "cache"))
    with pytest.raises(SystemExit):
        rc.pf_cache_dir(criar=False)
    monkeypatch.setenv("PAM_CACHE_PF", str(tmp_path / "OneDrive - X" / "cache"))
    with pytest.raises(SystemExit):
        rc.pf_cache_dir(criar=False)
    monkeypatch.setenv("PAM_CACHE_PF", str(tmp_path / "cache"))
    assert rc.pf_cache_dir(criar=False) == tmp_path / "cache"


def test_casamento_de_municipio_por_nome_normalizado_e_alias():
    dim = pd.DataFrame({"cod_municipio": ["1100114", "3303807", "1708254"],
                        "nome_municipio": ["Jaru", "Paraty", "Tabocão"], "uf": ["RO", "RJ", "TO"]})
    mapa, sem = rc.casar_municipios({("JARU", "RO"), ("PARATI", "RJ"), ("FORTALEZA DO TABOCAO", "TO"),
                                     ("JARU", "SP")}, dim)
    assert mapa == {("JARU", "RO"): "1100114", ("PARATI", "RJ"): "3303807",
                    ("FORTALEZA DO TABOCAO", "TO"): "1708254"}
    assert sem == [("JARU", "SP")]
