import pandas as pd

import export_frontend as ef

COD = "5107925"


def _grava(raiz, rel, df):
    p = raiz / f"{rel}.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p, index=False)


def _perfil(tmp_path, monkeypatch, com_stage2):
    """Roda build_perfil_rural sobre uma processed/ sintética com dim_municipio, stage1 e,
    se pedido, o stage2 — que, como no build_rural_profile, é o stage1 + agregados do CAR."""
    _grava(tmp_path, "dimensions/dim_municipio", pd.DataFrame({"cod_municipio": [COD], "uf": ["MT"]}))
    stage1 = pd.DataFrame({"cod_municipio": [COD], "uf": ["MT"],
                           "numero_estabelecimentos_censo": [812.0]})
    _grava(tmp_path, "municipality/rural_profile_stage1", stage1)
    if com_stage2:
        _grava(tmp_path, "municipality/rural_profile_stage2",
               stage1.assign(quantidade_cadastros_car=[1540.0]))
    monkeypatch.setattr(ef, "PROCESSED_DIR", tmp_path)
    return ef.build_perfil_rural()["mun"][COD]


def test_perfil_rural_usa_o_stage2_quando_existe(tmp_path, monkeypatch):
    # o --stage 2 grava os dois arquivos; o stage2 é o mais completo e deve vencer
    assert _perfil(tmp_path, monkeypatch, com_stage2=True).get("quantidade_cadastros_car") == 1540


def test_perfil_rural_cai_no_stage1_sem_o_stage2(tmp_path, monkeypatch):
    assert _perfil(tmp_path, monkeypatch, com_stage2=False).get("numero_estabelecimentos_censo") == 812
