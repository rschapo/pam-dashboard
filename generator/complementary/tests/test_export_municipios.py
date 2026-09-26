import json

import pandas as pd
import pytest

import export_municipios as em

RECIFE, NORONHA, BOA_ESPERANCA = "2611606", "2605459", "5101837"


def test_municipios_json_leva_nome_uf_e_microrregiao_de_cada_municipio(tmp_path, monkeypatch):
    pd.DataFrame({
        "cod_municipio": [RECIFE, NORONHA, BOA_ESPERANCA],
        "nome_municipio": ["Recife", "Fernando de Noronha", "Boa Esperança do Norte"],
        "uf": ["PE", "PE", "MT"],
        "cod_microrregiao": ["26017.0", "26019.0", None],
        "nome_microrregiao": ["Recife", "Fernando de Noronha", None],
        "nome_mesorregiao": ["Metropolitana de Recife", "Metropolitana de Recife", None],
    }).to_parquet(tmp_path / "dim_municipio.parquet", index=False)
    monkeypatch.setattr(em, "DIM", tmp_path)

    d = em.build_municipios()

    assert d["mun"][RECIFE] == ["Recife", "PE", "26017"]
    assert d["mun"][BOA_ESPERANCA] == ["Boa Esperança do Norte", "MT", None]   # instalado depois das microrregiões
    assert d["mic"] == {"26017": ["Recife", "PE", "Metropolitana de Recife"],
                        "26019": ["Fernando de Noronha", "PE", "Metropolitana de Recife"]}


def test_municipios_json_real_cobre_o_pais_e_concorda_com_a_pam():
    """O front completa o mun_info e o mic_info do pkg.json com este arquivo: onde os
    dois têm o município, a UF e a microrregião precisam ser as mesmas."""
    p, pkg = em.PUBLIC_DATA / "municipios.json", em.PUBLIC_DATA / "pkg.json"
    if not p.exists() or not pkg.exists():
        pytest.skip("municipios.json ou pkg.json ausentes")
    d = json.loads(p.read_text(encoding="utf-8"))
    pam = json.loads(pkg.read_text(encoding="utf-8"))
    dim = pd.read_parquet(em.DIM / "dim_municipio.parquet")

    assert len(d["mun"]) == len(dim)
    assert len(d["mic"]) == dim["cod_microrregiao"].dropna().nunique()
    for cod, i in pam["mun_info"].items():
        _, uf, mid = d["mun"][cod]
        assert uf == i["uf"], cod
        assert mid in (i["mid"], None), cod     # Boa Esperança do Norte: só a PAM a põe numa micro
    for mid, i in pam["mic_info"].items():
        assert d["mic"][mid][:2] == [i["n"], i["uf"]], mid
    # O que a PAM não lista: municípios sem lavoura e a micro de Fernando de Noronha.
    assert d["mun"][RECIFE] == ["Recife", "PE", "26017"]
    assert d["mun"][NORONHA][2] == "26019" and "26019" not in pam["mic_info"]
