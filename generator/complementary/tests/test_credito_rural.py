import pytest

import process_credito_rural as pcr
from common import PROCESSED_DIR


def test_nome_uf_resolve_grafias_do_sicor_e_municipio_novo():
    """O investimento do SICOR não traz código IBGE: o casamento por nome+UF precisa
    pegar as grafias do BCB e Boa Esperança do Norte, instalado em 2025."""
    if not (PROCESSED_DIR / "dimensions" / "dim_municipio.parquet").exists():
        pytest.skip("dim_municipio ausente")
    lookup = pcr._nome_uf_para_cod_ibge()
    chave = lambda nome, uf: pcr._norm_nome(nome) + "|" + uf
    assert lookup[chave("AÇU", "RN")] == "2400208"                          # Assú
    assert lookup[chave("SANTO ANTÔNIO DO LEVERGER", "MT")] == "5107800"    # de Leverger
    assert lookup[chave("SÃO LUIZ", "RR")] == "1400605"                     # São Luiz do Anauá
    assert lookup[chave("BOA ESPERANÇA DO NORTE", "MT")] == "5101837"
    assert lookup[chave("Sorriso", "MT")] == "5107925"
