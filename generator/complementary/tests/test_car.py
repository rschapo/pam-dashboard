import pytest

import process_car as pc


def test_hash_anonimo_determinista():
    a = pc._hash("MT-1234567-ABC")
    assert a == pc._hash("MT-1234567-ABC") and len(a) == 24


def test_status_map_carrega():
    m = pc._status_map()
    assert m.get("AT") == "ativo"
    assert m.get("Cancelado") == "cancelado"


def test_nivel_sobreposicao_bandas():
    assert pc._nivel_sobre(0.5) == "sem_sobreposicao_relevante"
    assert pc._nivel_sobre(3) == "mais_1_ate_5_percentual"
    assert pc._nivel_sobre(10) == "mais_5_ate_20_percentual"
    assert pc._nivel_sobre(50) == "mais_20_percentual"
    assert pc._nivel_sobre(None) is None


def test_geopandas_pipeline_importa_ou_skip():
    gpd = pytest.importorskip("geopandas", reason="geopandas não instalado neste ambiente")
    assert gpd is not None
