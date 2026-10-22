import json

import pytest

import export_censo_estabelecimentos as ec

CAB = {"V": "Valor", "D1C": "Município (Código)", "D1N": "Município", "D2N": "Variável", "D3N": "Ano",
       "D4N": "Grupos de atividade econômica", "D5N": "Condição do produtor em relação às terras",
       "D8N": "Tipologia"}


def _linha(cod, ativ, tipo, v, cond="Total"):
    return {"V": v, "D1C": cod, "D1N": "X", "D2N": "Número de estabelecimentos agropecuários", "D3N": "2017",
            "D4N": ativ, "D5N": cond, "D8N": tipo}


def test_simbolos_da_sidra_zero_e_sigilo_nao_se_confundem():
    assert ec.valor("-") == 0                 # zero absoluto
    assert ec.valor("X") is None              # sigilo: sem dado, nunca zero
    assert ec.valor("..") is None and ec.valor("...") is None
    assert ec.valor("1462") == 1462


def test_abertura_le_so_as_linhas_com_as_outras_classificacoes_em_total():
    linhas = [CAB,
              _linha("4300034", "Total", "Total", "120"),
              _linha("4300034", "Pecuária e criação de outros animais", "Total", "70"),
              _linha("4300034", "Pesca", "Total", "-"),
              _linha("4300034", "Aquicultura", "Total", "X"),
              _linha("4300034", "Pecuária e criação de outros animais", "Total", "999", cond="Proprietário")]
    por_mun, totais, sigilo = ec.ler_abertura(linhas, "Grupos de atividade econômica", ec.ATIVIDADES)
    assert totais == {"4300034": 120}
    assert por_mun["4300034"] == {"pecuaria": 70, "pesca": 0, "aquicultura": None}
    assert sigilo == 1


def test_censo_real_soma_o_total_oficial_e_tem_rs_e_sp_completos():
    p = ec.PUBLIC_DATA / "censo_estab_mun.json"
    if not p.exists():
        pytest.skip("censo_estab_mun.json ausente")
    d = json.loads(p.read_text(encoding="utf-8"))
    mun = d["mun"]
    assert sum(r["t"] for r in mun.values()) == ec.TOTAL_BRASIL
    rs = [r for c, r in mun.items() if c.startswith("43")]
    assert len(rs) == 497 and sum(r["t"] for r in rs) == 365_094
    assert sum(r["t"] for c, r in mun.items() if c.startswith("35")) == 188_620
    ka, kt = list(d["atividades"]), list(d["tipologias"])
    for c, r in mun.items():
        # atividades somam o total onde não há sigilo; familiar + não familiar também
        if None not in r["a"]:
            assert sum(r["a"]) == r["t"], c
        fam, nao = r["f"][kt.index("familiar")], r["f"][kt.index("nao_familiar")]
        if fam is not None and nao is not None:
            assert fam + nao == r["t"], c
    assert len(ka) == 9 and len(kt) == 7
