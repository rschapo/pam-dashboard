import sys

import pandas as pd
import pytest

import build_rural_profile as brp
import common
from common import RAW_DIR, uf_from_cod

SEM_PEVS = "1100015"   # município da dim_municipio sem nenhuma linha na PEVS

# Um município em 2025 com os três níveis da tabela 291 — o subtotal "1.3 - Madeira em
# tora" (= 1.3.1 + 1.3.2), os produtos (com grupo) e a abertura por espécie (sem grupo) —
# e uma linha da extração vegetal, que não é silvicultura.
NIVEIS_2025 = [
    ("5107925", 2025, "Silvicultura", "1.2 - Lenha", 30.0, "lenha"),
    ("5107925", 2025, "Silvicultura", "1.2.3 - Lenha de eucalipto", 30.0, None),
    ("5107925", 2025, "Silvicultura", "1.3 - Madeira em tora", 100.0, None),
    ("5107925", 2025, "Silvicultura", "1.3.1 - Madeira em tora para papel e celulose", 60.0,
     "madeira_tora_papel_celulose"),
    ("5107925", 2025, "Silvicultura",
     "1.3.1.3 - Madeira em tora de eucalipto para papel e celulose", 60.0, None),
    ("5107925", 2025, "Silvicultura", "1.3.2 - Madeira em tora para outras finalidades", 40.0,
     "madeira_tora_outros_fins"),
    ("5107925", 2025, "Extração vegetal", "7.2 - Lenha", 900.0, "extracao_madeireira"),
]


def _perfil(tmp_path, monkeypatch, *linhas):
    """Roda o stage1 sobre uma pevs_municipio sintética (sem MF, SNCR nem Censo)."""
    pevs = pd.DataFrame(list(linhas), columns=["cod_municipio", "ano", "tipo_atividade", "produto",
                                               "valor_producao_mil_reais", "grupo"])
    mun = sorted(set(pevs["cod_municipio"]) | {SEM_PEVS})
    pd.DataFrame({"cod_municipio": mun, "uf": [uf_from_cod(c) for c in mun]}).to_parquet(
        tmp_path / "dim_municipio.parquet", index=False)
    pevs.to_parquet(tmp_path / "pevs_municipio.parquet", index=False)
    monkeypatch.setattr(brp, "DIMS", tmp_path)
    monkeypatch.setattr(brp, "MUN", tmp_path)
    return brp.stage1().set_index("cod_municipio")


def test_valor_soma_so_o_nivel_produto_da_silvicultura(tmp_path, monkeypatch):
    p = _perfil(tmp_path, monkeypatch, *NIVEIS_2025)
    assert p.loc["5107925", "valor_producao_florestal"] == 130   # 30 + 60 + 40


def test_predominante_e_o_maior_produto_e_nunca_um_subtotal(tmp_path, monkeypatch):
    p = _perfil(tmp_path, monkeypatch, *NIVEIS_2025)
    # o subtotal 1.3 (100) não concorre; entre os produtos, 1.3.1 (60) ganha
    assert p.loc["5107925", "produto_florestal_predominante"] == \
        "1.3.1 - Madeira em tora para papel e celulose"


def test_usa_so_o_ultimo_ano_da_pevs(tmp_path, monkeypatch):
    p = _perfil(tmp_path, monkeypatch,
                ("5107925", 2024, "Silvicultura", "1.2 - Lenha", 500.0, "lenha"),
                ("5107925", 2025, "Silvicultura", "1.2 - Lenha", 30.0, "lenha"),
                ("3106200", 2024, "Silvicultura", "1.1 - Carvão vegetal", 70.0, "carvao_vegetal"))
    assert p.loc["5107925", "valor_producao_florestal"] == 30     # não acumula 2024
    # só produziu em 2024: fica sem silvicultura no ano de referência, e não com o 2024
    assert pd.isna(p.loc["3106200", "valor_producao_florestal"])
    assert not p.loc["3106200", "silvicultura_presente"]


def test_valor_zero_da_fonte_fica_zero_e_sem_predominante(tmp_path, monkeypatch):
    # "0" na SIDRA é valor positivo arredondado para zero (o "-" já chega nulo)
    p = _perfil(tmp_path, monkeypatch,
                ("3202108", 2025, "Silvicultura", "1.1 - Carvão vegetal", 0.0, "carvao_vegetal"),
                ("3202108", 2025, "Silvicultura", "1.2 - Lenha", 0.0, "lenha"))
    assert p.loc["3202108", "valor_producao_florestal"] == 0
    assert pd.isna(p.loc["3202108", "produto_florestal_predominante"])
    assert p.loc["3202108", "silvicultura_presente"]


def test_valor_sem_informacao_fica_nulo_e_nao_zero(tmp_path, monkeypatch):
    # sigiloso ("X") e não disponível ("..") chegam nulos da clean_num
    p = _perfil(tmp_path, monkeypatch,
                ("4205407", 2025, "Silvicultura", "1.2 - Lenha", None, "lenha"))
    assert pd.isna(p.loc["4205407", "valor_producao_florestal"])


def test_perfil_registra_o_ano_de_referencia_da_pevs(tmp_path, monkeypatch):
    p = _perfil(tmp_path, monkeypatch, *NIVEIS_2025,
                ("5107925", 2024, "Silvicultura", "1.2 - Lenha", 500.0, "lenha"))
    assert (p["ano_referencia_pevs"] == 2025).all()
    # sem PEVS: nulo, nunca zero — e o ano diz a que ano a ausência se refere
    assert pd.isna(p.loc[SEM_PEVS, "valor_producao_florestal"])
    assert not p.loc[SEM_PEVS, "silvicultura_presente"]


def test_perfil_real_fecha_com_o_total_do_ibge():
    """No perfil gerado da pevs_municipio real, o valor somado no Brasil é o Total da
    silvicultura do IBGE no ano de referência, e o predominante é sempre um produto."""
    bruto = RAW_DIR / "ibge" / "pevs" / "PEVS_municipios_completo.csv"
    if not bruto.exists():
        pytest.skip("consolidado PEVS ausente (os brutos ficam fora do repositório)")
    p = brp.stage1()
    ano = int(p["ano_referencia_pevs"].iloc[0])
    raw = pd.read_csv(bruto, sep=";", encoding="utf-8-sig", usecols=["Ano", "Tipo", "Cod_Categoria", "v"],
                      dtype={"Cod_Categoria": str})
    total = raw[(raw["Tipo"] == "Silvicultura") & (raw["Cod_Categoria"] == "0") & (raw["Ano"] == ano)]
    assert p["valor_producao_florestal"].sum() == pytest.approx(
        pd.to_numeric(total["v"], errors="coerce").sum(), rel=1e-9)
    produtos = {"1.1 - Carvão vegetal", "1.2 - Lenha",
                "1.3.1 - Madeira em tora para papel e celulose",
                "1.3.2 - Madeira em tora para outras finalidades",
                "2.1 - Acácia-negra (casca)", "2.2 - Eucalipto (folha)", "2.3 - Resina"}
    assert set(p["produto_florestal_predominante"].dropna()) <= produtos


def test_rodar_o_perfil_regrava_o_stage2_junto_com_o_stage1(tmp_path, monkeypatch):
    """Depois que uma fonte da Etapa 1 muda (aqui, o Censo corrigido), rodar o script de novo
    regrava também o stage2: o export_frontend prefere o stage2, e o da rodada anterior
    levaria os valores velhos para o perfil."""
    cod = "1100015"
    pd.DataFrame({"cod_municipio": [cod], "uf": [uf_from_cod(cod)]}).to_parquet(
        tmp_path / "dim_municipio.parquet", index=False)
    pd.DataFrame({"cod_municipio": [cod], "numero_estabelecimentos": [2886.0],
                  "area_estabelecimentos_ha": [90000.0]}).to_parquet(
        tmp_path / "censo_agro_municipio_summary.parquet", index=False)
    pd.DataFrame({"cod_municipio": [cod], "quantidade_cadastros": [3100],
                  "area_geometrica_uniao_ha": [510000.0], "percentual_sobreposicao": [4.2]}).to_parquet(
        tmp_path / "car_municipio_summary.parquet", index=False)
    # o stage2 da rodada anterior, com o Censo ainda dobrado
    pd.DataFrame({"cod_municipio": [cod], "uf": [uf_from_cod(cod)],
                  "numero_estabelecimentos_censo": [5772.0], "quantidade_cadastros_car": [3100]}).to_parquet(
        tmp_path / "rural_profile_stage2.parquet", index=False)
    for pasta in ("DIMS", "MUN", "GEO"):
        monkeypatch.setattr(brp, pasta, tmp_path)
    monkeypatch.setattr(common, "MANIFEST_DIR", tmp_path / "manifests")
    monkeypatch.setattr(sys, "argv", ["build_rural_profile.py"])   # sem argumentos, como na linha de comando

    brp.main()

    s2 = pd.read_parquet(tmp_path / "rural_profile_stage2.parquet").set_index("cod_municipio").loc[cod]
    assert s2.get("numero_estabelecimentos_censo") == 2886
    assert s2.get("quantidade_cadastros_car") == 3100   # é o stage2 de fato, com o CAR


def test_stage2_traz_a_estrutura_fundiaria_do_car(tmp_path, monkeypatch):
    """O stage2 leva a estrutura fundiária do CAR com o sufixo _car; município sem imóvel
    no CAR fica nulo, nunca zero."""
    cods = ["5107925", SEM_PEVS]
    base = pd.DataFrame({"cod_municipio": cods, "uf": [uf_from_cod(c) for c in cods]})
    pd.DataFrame({"cod_municipio": ["5107925"], "modulos_fiscais_mediana": [1.5],
                  "percentual_imoveis_ate_4_mf": [66.67], "percentual_imoveis_4_15_mf": [0.0],
                  "percentual_imoveis_acima_15_mf": [33.33], "percentual_area_ate_4_mf": [1.96],
                  "percentual_area_4_15_mf": [0.0], "percentual_area_acima_15_mf": [98.04]}).to_parquet(
        tmp_path / "car_estrutura_fundiaria.parquet", index=False)
    monkeypatch.setattr(brp, "GEO", tmp_path)
    monkeypatch.setattr(brp, "MUN", tmp_path)

    s2 = brp.stage2(base).set_index("cod_municipio")

    assert s2.at["5107925", "percentual_pequenos_imoveis_car"] == 66.67
    assert s2.at["5107925", "percentual_area_grandes_imoveis_car"] == 98.04
    assert s2.at["5107925", "mediana_modulos_fiscais_car"] == 1.5
    assert pd.isna(s2.at[SEM_PEVS, "percentual_pequenos_imoveis_car"])
