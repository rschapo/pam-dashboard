"""
build_rural_profile.py — Perfil estrutural municipal (Etapas 1 e 2, §6.9 e §7.x).

rural_profile_stage1: reúne SOMENTE agregados da Etapa 1 (módulo fiscal, SNCR,
Censo Agro, PEVS) por município. NÃO cruza com PAM/PPM (fica pronto p/ isso na fase
de integração). Da PEVS entra a silvicultura do último ano, só no nível de produto.

rural_profile_stage2: acrescenta os agregados do CAR e do MapBiomas (Etapa 2).

Cada rodada grava os dois. O export_frontend usa o stage2 quando ele existe: regravar
só o stage1 deixaria o stage2 da rodada anterior, com os valores velhos, alimentando o
perfil. Sem CAR nem MapBiomas, o stage2 sai igual ao stage1.

Ambos partem de dim_municipio (universo completo — municípios sem dados entram com
null, nunca zero). Saídas em data/processed/municipality/.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import PROCESSED_DIR, save_table, write_manifest  # noqa: E402

DIMS = PROCESSED_DIR / "dimensions"
MUN = PROCESSED_DIR / "municipality"
GEO = PROCESSED_DIR / "geospatial"


def _load(path, cols=None):
    p = Path(path)
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    return df[cols] if cols else df


def silvicultura_ultimo_ano(pevs: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Valor da silvicultura e produto predominante por município no último ano da PEVS.

    A pevs_municipio mistura subtotais do IBGE ("1.3 - Madeira em tora" = 1.3.1 + 1.3.2),
    produtos e, desde 2013, a abertura de cada produto por espécie. Só o nível produto tem
    `grupo`, e a soma dessas linhas fecha com o Total do IBGE em cada ano; somar tudo
    contaria a mesma produção duas ou três vezes. O predominante é o produto de maior
    valor (no empate, o primeiro rótulo); sem valor positivo, fica nulo.
    """
    sil = pevs[(pevs["tipo_atividade"] == "Silvicultura") & pevs["grupo"].notna()]
    ano = int(sil["ano"].max())
    sil = sil[sil["ano"] == ano]
    val = sil.groupby("cod_municipio")["valor_producao_mil_reais"].sum(min_count=1)
    por_produto = sil.groupby(["cod_municipio", "produto"], as_index=False)["valor_producao_mil_reais"].sum()
    pred = (por_produto[por_produto["valor_producao_mil_reais"] > 0]
            .sort_values(["valor_producao_mil_reais", "produto"], ascending=[False, True])
            .drop_duplicates("cod_municipio").set_index("cod_municipio")["produto"])
    out = val.rename("valor_producao_florestal").to_frame().join(
        pred.rename("produto_florestal_predominante"))
    return out.reset_index(), ano


def stage1() -> pd.DataFrame:
    dim = pd.read_parquet(DIMS / "dim_municipio.parquet")[["cod_municipio", "uf"]]
    prof = dim.copy()

    mf = _load(DIMS / "dim_modulo_fiscal.parquet", ["cod_municipio", "modulo_fiscal_ha"])
    if mf is not None:
        prof = prof.merge(mf, on="cod_municipio", how="left")

    sncr = _load(MUN / "sncr_municipio_summary.parquet")
    if sncr is not None:
        keep = sncr[["cod_municipio", "quantidade_imoveis_validos", "area_mediana_ha",
                     "modulos_fiscais_mediana", "percentual_imoveis_ate_4_mf",
                     "percentual_imoveis_4_15_mf", "percentual_imoveis_acima_15_mf"]].rename(columns={
            "quantidade_imoveis_validos": "quantidade_imoveis",
            "area_mediana_ha": "area_mediana_imovel_ha",
            "modulos_fiscais_mediana": "mediana_modulos_fiscais",
            "percentual_imoveis_ate_4_mf": "percentual_pequenos_imoveis",
            "percentual_imoveis_4_15_mf": "percentual_medios_imoveis",
            "percentual_imoveis_acima_15_mf": "percentual_grandes_imoveis"})
        prof = prof.merge(keep, on="cod_municipio", how="left")

    censo = _load(MUN / "censo_agro_municipio_summary.parquet")
    if censo is not None:
        prof = prof.merge(censo.rename(columns={
            "numero_estabelecimentos": "numero_estabelecimentos_censo",
            "area_estabelecimentos_ha": "area_estabelecimentos_censo_ha"}
        )[["cod_municipio", "numero_estabelecimentos_censo", "area_estabelecimentos_censo_ha"]],
            on="cod_municipio", how="left")

    pevs = _load(MUN / "pevs_municipio.parquet")
    if pevs is not None and not pevs.empty:
        sil, ano = silvicultura_ultimo_ano(pevs)
        prof = prof.merge(sil, on="cod_municipio", how="left")
        prof["silvicultura_presente"] = prof["valor_producao_florestal"].notna()
        prof["ano_referencia_pevs"] = ano
    return prof


def stage2(base: pd.DataFrame) -> pd.DataFrame:
    prof = base.copy()
    car = _load(GEO / "car_municipio_summary.parquet")
    if car is not None:
        prof = prof.merge(car[["cod_municipio", "quantidade_cadastros",
                               "area_geometrica_uniao_ha", "percentual_sobreposicao"]].rename(columns={
            "quantidade_cadastros": "quantidade_cadastros_car",
            "area_geometrica_uniao_ha": "area_car_uniao_ha",
            "percentual_sobreposicao": "percentual_sobreposicao_car"}),
            on="cod_municipio", how="left")
    mb = _load(MUN / "mapbiomas_municipio.parquet")
    if mb is not None and not mb.empty:
        ano = mb["ano"].max()
        cur = mb[mb["ano"] == ano]
        piv = cur.pivot_table(index="cod_municipio", columns="grupo_analitico",
                              values="area_ha", aggfunc="sum")
        for grp in ("agricultura", "pastagem", "silvicultura"):
            if grp in piv.columns:
                prof = prof.merge(piv[grp].rename(f"mapbiomas_{grp}_ha"),
                                  on="cod_municipio", how="left")
    return prof


def main():
    s1 = stage1()
    outs = save_table(s1, MUN / "rural_profile_stage1")
    write_manifest("rural_profile_stage1", source="Composição Etapa 1 (MF/SNCR/Censo/PEVS)",
                   reference_date=None, row_count=len(s1),
                   municipality_count=s1["cod_municipio"].nunique(), output_files=outs)
    print(f"[PERFIL] stage1: {len(s1):,} municípios, {s1.shape[1]} colunas")

    s2 = stage2(s1)
    outs2 = save_table(s2, MUN / "rural_profile_stage2")
    write_manifest("rural_profile_stage2", source="Composição Etapa 2 (+CAR/MapBiomas)",
                   reference_date=None, row_count=len(s2),
                   municipality_count=s2["cod_municipio"].nunique(), output_files=outs2)
    print(f"[PERFIL] stage2: {len(s2):,} municípios, {s2.shape[1]} colunas")


if __name__ == "__main__":
    main()
