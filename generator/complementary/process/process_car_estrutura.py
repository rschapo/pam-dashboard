"""
process_car_estrutura.py — Estrutura fundiária pelo CAR (Etapa 2).

Classifica cada imóvel do CAR pelo número de módulos fiscais e resume, por município, a
parcela de imóveis e de área em pequena (até 4 MF), média (mais de 4 até 15) e grande
propriedade (mais de 15) — as classes da Lei 8.629/1993 e do art. 12 da IE INCRA nº
5/2022. É a estrutura que o process_sncr daria, feita com os cadastros do CAR, que
cobrem o país; o SNCR é baixado à mão, por UF, e ainda não foi.

- Imóvel: cada cadastro não cancelado de car_imoveis_validos_<UF>, contado uma vez. Os
  cancelados ficam de fora, como nas camadas ambientais.
- Município: o principal, onde está a maior parte da área do imóvel
  (car_imovel_municipio_intersection_<UF>), o mesmo do car_municipio_summary; sem
  interseção, o declarado.
- Módulos fiscais: área geométrica ÷ módulo fiscal do município (dim_modulo_fiscal),
  sem a área declarada, como no resto do CAR. Imóvel com área geométrica zero ou em
  município sem módulo fiscal fica sem classe e fora dos percentuais.
- Área por classe: soma das áreas dos imóveis, sem descontar a sobreposição. Diz como a
  área cadastrada se divide entre as classes, não quanto do território cada uma ocupa.

Município sem imóvel no CAR não tem linha. Onde nenhum imóvel tem classe, as contagens
e os percentuais ficam nulos, nunca zero.

Conferência: o SICAR traz o número de módulos de cada imóvel, calculado com a área
declarada e o módulo fiscal do município declarado. A classe que ele dá é comparada
com a daqui, por UF, no manifesto.

Saídas:
  data/processed/geospatial/car_estrutura_fundiaria.parquet | .csv
  data/manifests/car_estrutura_fundiaria.json
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # p/ importar _stats via orquestrador
from common import PROCESSED_DIR, UFS, save_table, write_manifest  # noqa: E402
from _stats import FAIXAS_MF_ANALITICA, FAIXAS_MF_LEGAL  # noqa: E402

GEO = PROCESSED_DIR / "geospatial"
DIMS = PROCESSED_DIR / "dimensions"
METODO = "área geométrica ÷ módulo fiscal do município principal; sem cancelados"
CLASSES = [nome for nome, *_ in FAIXAS_MF_LEGAL]              # ate_4_mf, mais_4_ate_15_mf, mais_15_mf
SUFIXO = {"ate_4_mf": "ate_4_mf", "mais_4_ate_15_mf": "4_15_mf", "mais_15_mf": "acima_15_mf"}
# as três primeiras faixas analíticas repartem a pequena propriedade, como no SNCR
PEQUENAS = {"ate_1_mf": "quantidade_ate_1_mf", "mais_1_ate_2_mf": "quantidade_1_2_mf",
            "mais_2_ate_4_mf": "quantidade_2_4_mf"}


def classe(modulos: pd.Series, faixas=FAIXAS_MF_LEGAL) -> pd.Series:
    """Faixa de cada valor, com os limites de _stats.faixa_mf: o zero entra na primeira
    faixa e as demais são (lo, hi]. Nulo continua nulo."""
    bordas = [faixas[0][1]] + [hi for _, _, hi in faixas]
    return pd.cut(modulos, bins=bordas, labels=[n for n, *_ in faixas],
                  right=True, include_lowest=True).astype(object)


def classificar(v: pd.DataFrame, mf: pd.Series) -> pd.DataFrame:
    """Módulos fiscais e classes de imóveis que já têm `cod_municipio`."""
    area = v["area_geometrica_ha"].where(v["area_geometrica_ha"] > 0)
    v = v.assign(modulos_fiscais=area / v["cod_municipio"].map(mf))
    v["classe"] = classe(v["modulos_fiscais"])
    v["faixa"] = classe(v["modulos_fiscais"], FAIXAS_MF_ANALITICA)
    v["classe_sicar"] = classe(v["modulos_fiscais_declarado"])
    return v


def imoveis_uf(uf: str, mf: pd.Series) -> tuple[pd.DataFrame, int]:
    """Imóveis não cancelados da UF, classificados, e quantos cancelados saíram."""
    v = pd.read_parquet(GEO / f"car_imoveis_validos_{uf}.parquet",
                        columns=["id_car_hash", "cod_municipio_declarado", "area_geometrica_ha",
                                 "modulos_fiscais_declarado", "situacao_car_padronizada"])
    cancelado = v["situacao_car_padronizada"] == "cancelado"
    v = v[~cancelado].drop_duplicates("id_car_hash")
    i = pd.read_parquet(GEO / f"car_imovel_municipio_intersection_{uf}.parquet",
                        columns=["id_car_hash", "cod_municipio", "municipio_principal"])
    princ = (i[i["municipio_principal"]].drop_duplicates("id_car_hash")
             .set_index("id_car_hash")["cod_municipio"])
    v = v.assign(cod_municipio=v["id_car_hash"].map(princ).fillna(v["cod_municipio_declarado"]),
                 uf_origem=uf)
    return classificar(v, mf), int(cancelado.sum())


def resumir(v: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por município a partir dos imóveis classificados."""
    g = v.groupby("cod_municipio")
    out = g.agg(quantidade_imoveis=("classe", "size"), area_imoveis_ha=("area_geometrica_ha", "sum"))
    out["quantidade_sem_modulo"] = v["classe"].isna().groupby(v["cod_municipio"]).sum()
    com = v[v["classe"].notna()]
    out["modulos_fiscais_mediana"] = com.groupby("cod_municipio")["modulos_fiscais"].median()

    q = (com.groupby(["cod_municipio", "classe"]).size().unstack()
         .reindex(index=out.index, columns=CLASSES))
    a = (com.groupby(["cod_municipio", "classe"])["area_geometrica_ha"].sum().unstack()
         .reindex(index=out.index, columns=CLASSES))
    f = (com.groupby(["cod_municipio", "faixa"]).size().unstack()
         .reindex(index=out.index, columns=list(PEQUENAS)))
    tem = q.notna().any(axis=1)                  # município com ao menos um imóvel classificado
    q, a, f = q.where(~tem, q.fillna(0)), a.where(~tem, a.fillna(0.0)), f.where(~tem, f.fillna(0))
    for faixa, col in PEQUENAS.items():
        out[col] = f[faixa].astype("Int64")
    out["quantidade_4_15_mf"] = q["mais_4_ate_15_mf"].astype("Int64")
    out["quantidade_acima_15_mf"] = q["mais_15_mf"].astype("Int64")
    for c in CLASSES:
        out[f"area_{SUFIXO[c]}_ha"] = a[c].round(4)
    for c in CLASSES:
        out[f"percentual_imoveis_{SUFIXO[c]}"] = (100.0 * q[c] / q.sum(axis=1, min_count=1)).round(2)
    for c in CLASSES:
        out[f"percentual_area_{SUFIXO[c]}"] = (100.0 * a[c] / a.sum(axis=1, min_count=1)).round(2)
    out["area_imoveis_ha"] = out["area_imoveis_ha"].round(4)
    out["modulos_fiscais_mediana"] = out["modulos_fiscais_mediana"].round(4)
    out["metodo"] = METODO
    return out.reset_index()


def concordancia(v: pd.DataFrame) -> float | None:
    """% dos imóveis com as duas classes em que a do SICAR é a mesma daqui."""
    ambos = v["classe"].notna() & v["classe_sicar"].notna()
    return round(100.0 * float((v.loc[ambos, "classe"] == v.loc[ambos, "classe_sicar"]).mean()), 2) \
        if ambos.any() else None


def main():
    mf = pd.read_parquet(DIMS / "dim_modulo_fiscal.parquet").set_index("cod_municipio")["modulo_fiscal_ha"]
    partes, por_uf, cancelados, ausentes = [], {}, 0, []
    for uf in UFS:
        if not (GEO / f"car_imoveis_validos_{uf}.parquet").exists():
            ausentes.append(uf)
            continue
        v, n_cancel = imoveis_uf(uf, mf)
        cancelados += n_cancel
        por_uf[uf] = concordancia(v)
        partes.append(v[["cod_municipio", "area_geometrica_ha", "modulos_fiscais",
                         "classe", "faixa", "classe_sicar"]])
    todos = pd.concat(partes, ignore_index=True)
    df = resumir(todos)

    brasil = {c: int((todos["classe"] == c).sum()) for c in CLASSES}
    brasil_sicar = {c: int((todos["classe_sicar"] == c).sum()) for c in CLASSES}
    conc = concordancia(todos)
    sem_classe = int(todos["classe"].isna().sum())
    avisos = [f"UFs sem CAR processado: {', '.join(ausentes)}"] if ausentes else []

    outs = save_table(df, GEO / "car_estrutura_fundiaria")
    write_manifest("car_estrutura_fundiaria", source="SICAR — CAR; INCRA — módulo fiscal",
                   reference_date=None, row_count=len(df),
                   municipality_count=df["cod_municipio"].nunique(),
                   rejected_rows=cancelados, output_files=outs, warnings=avisos,
                   extra={"metodo": METODO, "imoveis": len(todos), "cancelados_excluidos": cancelados,
                          "imoveis_sem_classe": sem_classe,
                          "imoveis_por_classe": brasil, "imoveis_por_classe_sicar": brasil_sicar,
                          "concordancia_classe_sicar_pct": {"BR": conc, **por_uf}})
    print(f"[CAR/ESTRUTURA] {len(df):,} municípios · {len(todos):,} imóveis (sem {cancelados:,} cancelados) "
          f"· sem classe {sem_classe:,}")
    print(f"  por classe: {brasil}")
    print(f"  pelo SICAR: {brasil_sicar} · mesma classe em {conc}% dos imóveis")


if __name__ == "__main__":
    main()
