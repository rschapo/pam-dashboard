import process_modulo_fiscal as pm


def test_norm_remove_acentos_e_caixa():
    assert pm._norm("São Félix do Xingu") == "sao felix do xingu"
    assert pm._norm("  ARAGUAÍNA ") == "araguaina"


def test_find_col_por_palavras_chave():
    cols = ["CD_MUN", "NOME_MUNIC", "MODULO_FISCAL_HA", "UF"]
    assert pm._find_col(cols, "modulo", "fiscal") == "MODULO_FISCAL_HA"
    assert pm._find_col(cols, "uf") == "UF"
    assert pm._find_col(cols, "inexistente") is None
