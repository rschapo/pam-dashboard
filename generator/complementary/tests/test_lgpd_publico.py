"""Não-identificação em public/ (regra de dados pessoais de 21/10/2026, opção A).
Varre o public/ como ele está: se um destes testes falhar, o painel não pode ser publicado."""
import json

import pandas as pd
import pytest

import receita_common as rc
import verificar_lgpd_publico as v

ARQS = v.arquivos_texto()


def test_public_tem_os_arquivos_que_o_verificador_le():
    assert any(p.name == "index.html" for p in ARQS)
    assert any(p.suffix == ".json" for p in ARQS)


def test_nenhum_cnpj_telefone_ou_arroba_em_public():
    achados = {str(p): a for p in ARQS if (a := v.achar_padroes(p))}
    assert achados == {}


def test_arquivos_de_produtores_e_contas_sem_chave_de_identificacao():
    arqs = v.arquivos_pessoais()
    if not arqs:
        pytest.skip("nenhum JSON de produtores ou contas-chave em public/data")
    achados = {p.name: c for p in arqs if (c := v.chaves_proibidas(json.loads(p.read_text(encoding="utf-8"))))}
    assert achados == {}


def _lugares():
    dim = pd.read_parquet(rc.PROCESSED_DIR / "dimensions" / "dim_municipio.parquet", columns=["nome_municipio"])
    return set(dim["nome_municipio"].map(v.norm).str.replace(r"[^A-Z ]", " ", regex=True).str.split().str.join(" "))


def test_nenhum_nome_da_amostra_de_produtores_pf_em_public():
    cache = rc.pf_cache_existente()
    bases = sorted(cache.glob("produtores_base_*.parquet")) if cache else []
    if not bases:
        pytest.skip("base local de produtores ausente nesta máquina: amostra de nomes não verificada")
    nomes = v.amostra_nomes(bases[-1], 500, excluir=_lugares())
    assert len(nomes) == 500
    assert v.achar_nomes(nomes, ARQS) == {}


# ── o verificador acusa de verdade ─────────────────────────────────────────────
def test_verificador_acusa_cnpj_telefone_arroba_e_nome_injetados(tmp_path):
    ruim = tmp_path / "data" / "produtores_mun.json"
    ruim.parent.mkdir()
    ruim.write_text(json.dumps({"mun": {"3550308": {"nome": "José da Silva Pereira", "cnpj": "12345678000190",
                                                    "tel": "(19) 99876-5432", "email": "a@b.com"}}},
                               ensure_ascii=False), encoding="utf-8")
    achados = v.achar_padroes(ruim)
    assert any(a.startswith("CNPJ 12345678000190") for a in achados)
    assert any(a.startswith("telefone") for a in achados)
    assert "@ num JSON de dados" in achados
    assert set(v.chaves_proibidas(json.loads(ruim.read_text(encoding="utf-8")))) >= \
        {"/mun/3550308/nome", "/mun/3550308/cnpj", "/mun/3550308/tel", "/mun/3550308/email"}
    assert v.achar_nomes(["JOSE DA SILVA PEREIRA"], [ruim]) == {str(ruim): ["JOSE DA SILVA PEREIRA"]}
    mascara = tmp_path / "x.html"
    mascara.write_text("<p>12.345.678/0001-90</p>", encoding="utf-8")
    assert v.achar_padroes(mascara) == ["CNPJ 12.345.678/0001-90"]


def test_verificador_nao_confunde_coordenada_nem_nome_dentro_de_outro(tmp_path):
    ok = tmp_path / "geo.json"
    ok.write_text('{"c":[-47.12345678901234,-23.55052012345678],"n":"Josefina","anos":"2004-2025"}',
                  encoding="utf-8")
    assert v.achar_padroes(ok) == []
    assert v.achar_nomes(["JOSE FINA"], [ok]) == {}
    assert v.achar_nomes(["JOSEFINA"], [ok]) == {str(ok): ["JOSEFINA"]}
