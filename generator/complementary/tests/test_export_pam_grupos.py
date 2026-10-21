import json

import pandas as pd
import pytest

import export_pam_grupos as epg

CROP = [
    {"cultura": "Soja (em grão)", "tipo": "TEM", "COL": "1", "pai": ""},
    {"cultura": "Cana-de-açúcar", "tipo": "TEM", "COL": "0", "pai": ""},
    {"cultura": "Café (em grão) Total", "tipo": "PER", "COL": "0", "pai": ""},
    {"cultura": "Café (em grão) Arábica", "tipo": "PER", "COL": "0", "pai": "Café (em grão) Total"},
    {"cultura": "Laranja", "tipo": "PER", "COL": "0", "pai": ""},
]
GRUPOS = [
    {"grupo": "cana", "rotulo": "Cana-de-açúcar", "subgrupo": "", "cultura": "Cana-de-açúcar",
     "versao": "2026-10-21", "origem": "manual"},
    {"grupo": "cafe", "rotulo": "Café", "subgrupo": "", "cultura": "Café (em grão) Total",
     "versao": "2026-10-21", "origem": "manual"},
]
DOM = [
    {"cultura": "Soja (em grão)", "categoria": "Grãos e oleaginosas"},
    {"cultura": "Cana-de-açúcar", "categoria": "Cana"},
    {"cultura": "Café (em grão) Total", "categoria": "Café"},
    {"cultura": "Café (em grão) Arábica", "categoria": ""},
    {"cultura": "Laranja", "categoria": "Citros"},
]


def test_aborta_se_parte_do_cafe_entra_num_grupo():
    ruim = GRUPOS + [{**GRUPOS[1], "cultura": "Café (em grão) Arábica"}]
    with pytest.raises(SystemExit, match="parte de"):
        epg.ler_tabelas(CROP, ruim, DOM)


def test_aborta_se_parte_do_cafe_ganha_categoria():
    ruim = [d if d["cultura"] != "Café (em grão) Arábica" else {**d, "categoria": "Café"} for d in DOM]
    with pytest.raises(SystemExit, match="parte de"):
        epg.ler_tabelas(CROP, GRUPOS, ruim)


def test_aborta_se_cultura_fica_sem_categoria():
    with pytest.raises(SystemExit, match="sem categoria"):
        epg.ler_tabelas(CROP, GRUPOS, [d for d in DOM if d["cultura"] != "Laranja"])


def test_grupos_de_maquina_saem_do_crop_groups_sem_as_partes():
    g, cat, filhas = epg.ler_tabelas(CROP, GRUPOS, DOM)
    assert g["col"]["culturas"] == ["Soja (em grão)"]
    assert g["tra"]["culturas"] == ["Cana-de-açúcar"]          # temporária fora de COL
    assert "Café (em grão) Arábica" not in cat and filhas == {"Café (em grão) Arábica": "Café (em grão) Total"}
    assert g["cana"]["def"] == "lista de culturas: definição 2026-10-21 · 1 cultura"


def test_build_no_ultimo_ano_com_cafe_so_pelo_total_e_floresta_da_pevs():
    A, B, C = "3500105", "3500204", "3500303"
    pam = pd.DataFrame([
        (A, 2024, "Cana-de-açúcar", 999),                       # ano anterior: fora
        (A, 2025, "Cana-de-açúcar", 50), (A, 2025, "Soja (em grão)", 100),
        (A, 2025, "Café (em grão) Total", 30), (A, 2025, "Café (em grão) Arábica", 30),
        (B, 2025, "Laranja", float("nan")),                     # linha publicada sem número
    ], columns=["Cod_Municipio", "Ano", "Cultura", "Area_Colhida_ha"])
    pevs = pd.DataFrame([
        (A, 2025, "Área plantada (silvicultura)", 80), (A, 2025, "Área plantada (silvicultura)", 90),
        (C, 2025, "Área plantada (silvicultura)", 10), (C, 2024, "Área plantada (silvicultura)", 500),
    ], columns=["cod_municipio", "ano", "tipo_atividade", "area_ha"])

    d = epg.build_pam_grupos(pam, pevs, epg.ler_tabelas(CROP, GRUPOS, DOM))

    assert (d["ano_pam"], d["ano_pevs"]) == (2025, 2025)
    a = d["mun"][A]
    assert a["t"] == 180                                         # 50 + 100 + 30, sem o Arábica
    assert a["g"] == {"cana": 50, "cafe": 30, "col": 100, "tra": 50, "floresta": 170}
    assert a["c"]["Floresta plantada"] == 170 and a["d"] == "Floresta plantada"
    # B tem PAM (a linha sem número) e nada somado: total 0, sem cultura dominante
    assert d["mun"][B] == {"t": 0}
    # C só tem floresta: sem "t" (sem lavoura publicada), mas com categoria
    assert "t" not in d["mun"][C] and d["mun"][C]["d"] == "Floresta plantada"


def test_dominante_desempata_pela_ordem_das_categorias():
    assert epg.dominante({"Cana": 10, "Café": 10}) == "Cana"
    assert epg.dominante({"Cana": 0}) is None


def test_pam_grupos_real_bate_com_o_pkg_e_nao_tem_parte_do_cafe():
    p, pkg = epg.PUBLIC_DATA / "pam_grupos.json", epg.PUBLIC_DATA / "pkg.json"
    if not p.exists() or not pkg.exists():
        pytest.skip("pam_grupos.json ou pkg.json ausentes")
    d = json.loads(p.read_text(encoding="utf-8"))
    k = json.loads(pkg.read_text(encoding="utf-8"))
    i = k["anos"].index(d["ano_pam"])
    filhas = set(k.get("filhas", {}))
    assert filhas == {"Café (em grão) Arábica", "Café (em grão) Canephora"}
    for g, o in d["grupos"].items():
        assert not filhas & set(o["culturas"]), g
        if o["fonte"] != "pam":
            continue
        # a soma municipal do grupo é a soma estadual das culturas dele no mesmo ano
        uf = sum(k["est_data"][u].get(c, {"a": [0] * len(k["anos"])})["a"][i]
                 for u in k["est_data"] for c in o["culturas"])
        mun = sum(r.get("g", {}).get(g, 0) for r in d["mun"].values())
        assert mun == pytest.approx(uf, abs=len(d["mun"])), g     # arredondamento por município
    # o total do município é o do pkg.json (já sem as partes do café)
    t = sum(r.get("t", 0) for r in d["mun"].values())
    assert t == pytest.approx(sum(m["a"][i] for m in k["mun_data"].values()), abs=len(d["mun"]))
    # a dominante é a categoria de maior área de cada município
    for cod, r in d["mun"].items():
        if r.get("c"):
            assert r["d"] == epg.dominante(r["c"]), cod
        assert set(r.get("c", {})) <= set(d["categorias"]), cod
