import pandas as pd
import pytest

import process_modulo_fiscal as pm
from common import PROCESSED_DIR

# linhas do PDF de 2013 como o pypdf as extrai no modo layout
ABAETETUBA = ("1500107     ABAETETUBA                                           011    4     70      "
              "B2-5      3      75      1.362          79.985,6     1.610,6        A, PA")
# instalado em 2013: sem imóveis cadastrados e com a superfície em "***"
RINCAO = ("4220000    BALNEÁRIO RINCÃO               019  2   20         A2-2  2     30    0     "
          "          0,0           ***  L")


def test_norm_remove_acentos_e_caixa():
    assert pm._norm("São Félix do Xingu") == "sao felix do xingu"
    assert pm._norm("  ARAGUAÍNA ") == "araguaina"


def test_linha_2013_le_os_indices_e_tira_o_numero_de_ordem_da_zona():
    assert pm.ler_linha_2013(ABAETETUBA) == {
        "cod_municipio": "1500107", "nome_incra": "ABAETETUBA", "zona_pecuaria": 4,
        "modulo_fiscal_ha": 70.0, "ztm_2013": "B2", "fmp_2013": 3.0}
    r = pm.ler_linha_2013(RINCAO)
    assert (r["modulo_fiscal_ha"], r["ztm_2013"], r["fmp_2013"]) == (20.0, "A2", 2.0)


def test_tabela_2013_so_conta_como_falha_linha_com_codigo():
    linhas = ["UF - PARÁ", "            1.547.321,8 22.886,6", ABAETETUBA,
              "1500206    ACARÁ    sem os índices"]
    t13, falhas = pm.ler_tabela_2013(linhas)
    assert list(t13["cod_municipio"]) == ["1500107"]
    assert falhas == ["1500206    ACARÁ    sem os índices"]


IE = ("Art. 15. Esta Instrução Especial entra em vigor. ANEXO III ZONAS TÍPICAS DE MÓDULO POR "
      "REGIÃO GEOGRÁFICA IMEDIATA Limite de Aquisição por estrangeiro (ha) MG Abaeté 310070 A3 2 45 "
      "DF Distrito Federal 530001 2 15 PA Almeirim - Porto de Moz 150019 C1 4 165 "
      "ANEXO IV ÍNDICES BÁSICOS CADASTRAIS DO INCRA POR MUNICÍPIO Código Região Geográfica Imediata "
      "Abadia de Goiás GO A1 2 24 2 5 5200050 520001 Abaeté MG A3 3 40 2 15 3100203 310070")


def test_ie_2022_da_a_zona_de_cada_regiao_e_o_trecho_do_anexo_iv():
    ztm, iv = pm.ler_ie_2022(IE)
    assert ztm == {"310070": "A3", "530001": None, "150019": "C1"}   # o DF vem sem zona
    assert iv.to_dict("records") == [
        {"cod_municipio": "5200050", "ztm": "A1", "zp": 2, "mf": 24.0, "fmp": 2.0},
        {"cod_municipio": "3100203", "ztm": "A3", "zp": 3, "mf": 40.0, "fmp": 2.0}]


def _t13(*linhas):
    return pd.DataFrame(linhas, columns=["cod_municipio", "nome_incra", "zona_pecuaria",
                                         "modulo_fiscal_ha", "ztm_2013", "fmp_2013"])


T13 = _t13(("3100203", "ABAETÉ", 3, 40.0, "A3", 3.0),
           ("1500131", "ABEL FIGUEIREDO", 4, 70.0, "C1", 4.0),
           ("5300108", "BRASÍLIA", 3, 5.0, "A1", 2.0))
DIM = pd.DataFrame({"cod_municipio": ["3100203", "1500131", "5300108", "5101837"],
                    "nome_municipio": ["Abaeté", "Abel Figueiredo", "Brasília", "Boa Esperança do Norte"],
                    "uf": ["MG", "PA", "DF", "MT"],
                    "cod_regiao_imediata": ["310070", "150010", "530001", "510010"]})
# a IE de 2022 baixou a FMP de Abaeté; a zona de Abel Figueiredo mudou sem mudar a FMP
P22 = pd.DataFrame({"cod_municipio": ["3100203"], "mf": [40.0], "zp": [3], "fmp_antiga": [3.0],
                    "fmp": [2.0], "ztm_antiga": ["A3"], "ztm": ["A3"]})
ZTM = {"310070": "A3", "150010": "B3", "530001": None}


def test_combinar_aplica_a_fmp_de_2022_e_a_zona_da_regiao_imediata():
    df, nao, faltam, avisos = pm.combinar(T13, P22, ZTM, DIM)
    d = df.set_index("cod_municipio")
    assert list(df.columns) == pm.CAMPOS
    assert d.at["3100203", "fracao_minima_parcelamento_ha"] == 2.0    # da planilha de 2022
    assert d.at["1500131", "fracao_minima_parcelamento_ha"] == 4.0    # a de 2013
    assert d.at["1500131", "zona_tipica_modulo"] == "B3"              # da região, não a de 2013
    assert d.at["5300108", "zona_tipica_modulo"] == "A1"              # região sem zona: a de 2013
    assert "2013" in d.at["5300108", "observacao"] and pd.isna(d.at["3100203", "observacao"])
    assert (df["modulo_fiscal_ha"].tolist(), avisos, len(nao)) == ([40.0, 70.0, 5.0], [], 0)
    assert faltam["cod_municipio"].tolist() == ["5101837"]


def test_combinar_avisa_quando_a_planilha_contradiz_2013():
    p22 = P22.assign(mf=[30.0])
    _, _, _, avisos = pm.combinar(T13, p22, ZTM, DIM)
    assert avisos == ["planilha de 2022: o módulo fiscal difere da tabela de 2013 em 1 municípios"]


def test_conferir_anexo_iv_conta_divergencias_por_campo():
    df, *_ = pm.combinar(T13, P22, ZTM, DIM)
    iv = pd.DataFrame([{"cod_municipio": "3100203", "ztm": "A3", "zp": 3, "mf": 40.0, "fmp": 2.0},
                       {"cod_municipio": "1500131", "ztm": "B3", "zp": 4, "mf": 75.0, "fmp": 4.0}])
    assert pm.conferir_anexo_iv(df, iv) == {"municipios": 2, "divergencias": {
        "ausentes": 0, "modulo_fiscal_ha": 1, "fracao_minima_parcelamento_ha": 0,
        "zona_tipica_modulo": 0, "zona_pecuaria": 0}}


def test_dim_real_tem_os_indices_de_todos_os_municipios_do_incra():
    p = PROCESSED_DIR / "dimensions" / "dim_modulo_fiscal.parquet"
    if not p.exists():
        pytest.skip("dim_modulo_fiscal ainda não gerada")
    d = pd.read_parquet(p)
    assert len(d) == d["cod_municipio"].nunique() >= 5569
    assert d["modulo_fiscal_ha"].between(5, 110).all()
    assert d[["fracao_minima_parcelamento_ha", "zona_tipica_modulo", "zona_pecuaria"]].notna().all().all()
    assert d.set_index("cod_municipio").at["5300108", "modulo_fiscal_ha"] == 5   # Brasília
