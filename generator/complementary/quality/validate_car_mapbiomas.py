"""
validate_car_mapbiomas.py — confere as camadas ambientais dissolvidas do CAR
contra o MapBiomas, por UF.

O CAR é declaratório e só cobre parte do território; o MapBiomas classifica o
território inteiro por satélite. Cada camada é comparada de um jeito:

  vegetação nativa × formação natural. A vegetação se espalha pelo território
    todo, inclusive por terra pública e área não cadastrada, que ficam fora do
    CAR. A razão direta mede sobretudo a cobertura do CAR, então ela é dividida
    pela cobertura da UF (área dos imóveis ÷ território) antes de ser lida.
  área consolidada × agropecuária (agricultura + pastagem). A agropecuária está
    quase toda dentro de imóvel privado, então a razão é lida direto. Ela fica
    naturalmente abaixo de 1 onde houve abertura depois de 22/07/2008, que não
    é área consolidada pela lei.

As referências saem das classes do MapBiomas, no ano mais recente. Formação
natural inclui as áreas úmidas — floresta alagável e campo alagado são vegetação
nativa, e sem elas a Amazônia e o Pantanal sairiam distorcidos; é a mesma
definição do domínio de uso do solo do painel. Agropecuária é o nível 1 do
MapBiomas: agricultura, pastagem, mosaico de usos e silvicultura.

Na Bahia entram as medidas compostas (ver docs/CAR_LIMITATIONS.md). A correlação
por município mostra se a distribuição espacial acompanha, mesmo quando o nível
difere.

Sinaliza a UF cuja razão fique fora de [0,5; 1,5] ou cuja correlação fique
abaixo de 0,7: é onde a base nacional pode estar parcial, como estava a área
consolidada da Bahia. Sinal não é veredito — a UF sinalizada precisa de
investigação, como a que foi feita com o CEFIR.

Grava data/processed/state/car_mapbiomas_uf (.parquet e .csv).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "process"))
from common import PROCESSED_DIR, save_table  # noqa: E402
from export_car import UF_EXCLUIDA, camadas_ambientais  # noqa: E402

FAIXA = (0.5, 1.5)
R_MIN = 0.7
GRUPOS = {
    "natural_ha": ["formacao_florestal", "formacao_savanica", "formacao_campestre",
                   "area_umida", "outras_formacoes_naturais"],
    "agropecuaria_ha": ["agricultura", "pastagem", "mosaico_de_usos", "silvicultura"],
}
# campo → (referência do MapBiomas, normaliza pela cobertura do CAR?)
PARES = {
    "vn": ("natural_ha", True),
    "ac": ("agropecuaria_ha", False),
}


def _referencias() -> tuple[pd.DataFrame, int]:
    p = PROCESSED_DIR / "municipality" / "mapbiomas_municipio.parquet"
    ano = int(pd.read_parquet(p, columns=["ano"])["ano"].max())
    mb = pd.read_parquet(p, columns=["cod_municipio", "grupo_analitico", "area_ha"],
                         filters=[("ano", "==", ano)])
    ref = pd.DataFrame({nome: mb[mb["grupo_analitico"].isin(g)].groupby("cod_municipio")["area_ha"].sum()
                        for nome, g in GRUPOS.items()})
    return ref.rename_axis("cod_municipio").reset_index(), ano


def run() -> pd.DataFrame:
    dim = pd.read_parquet(PROCESSED_DIR / "dimensions" / "dim_municipio.parquet")
    car = pd.read_parquet(PROCESSED_DIR / "geospatial" / "car_municipio_summary.parquet",
                          columns=["cod_municipio", "area_geometrica_uniao_ha"])
    ref, ano = _referencias()
    amb, _, _ = camadas_ambientais(dim)
    d = (dim[["cod_municipio", "uf", "area_municipal_ha"]]
         .merge(car, on="cod_municipio", how="left")
         .merge(ref, on="cod_municipio", how="left")
         .merge(amb, left_on="cod_municipio", right_index=True, how="left"))
    print(f"MapBiomas {ano}; CAR dissolvido, sem cancelados")

    linhas = []
    for uf, g in d.groupby("uf"):
        # A base de imóveis do DF está incompleta: sem cobertura confiável.
        cobertura = (math.nan if uf == UF_EXCLUIDA
                     else g["area_geometrica_uniao_ha"].sum() / g["area_municipal_ha"].sum())
        lin = {"uf": uf, "municipios": len(g), "cobertura_car": cobertura}
        sinais = []
        for campo, (ref, normaliza) in PARES.items():
            if campo not in g or g[campo].isna().all():
                continue
            ok = g[campo].notna() & g[ref].notna()
            car_ha, ref_ha = g.loc[ok, campo].sum(), g.loc[ok, ref].sum()
            razao = car_ha / ref_ha if ref_ha else math.nan
            lida = razao / cobertura if normaliza else razao
            r = g.loc[ok, campo].corr(g.loc[ok, ref])
            lin.update({f"{campo}_ha": car_ha, f"{campo}_ref_ha": ref_ha,
                        f"{campo}_razao": razao, f"{campo}_lida": lida, f"{campo}_r": r})
            # Sem cobertura (DF) ou com um município só, não há o que ler: não é sinal.
            if pd.notna(lida) and not (FAIXA[0] <= lida <= FAIXA[1]):
                sinais.append(f"{campo} {lida:.2f}")
            if pd.notna(r) and r < R_MIN:
                sinais.append(f"{campo} r={r:.2f}")
        lin["sinais"] = "; ".join(sinais)
        linhas.append(lin)
    return pd.DataFrame(linhas)


def main():
    t = run()
    save_table(t, PROCESSED_DIR / "state" / "car_mapbiomas_uf")
    pct = lambda v: "   —" if pd.isna(v) else f"{100 * v:4.0f}%"
    num = lambda v: "   —" if pd.isna(v) else f"{v:4.2f}"
    print("UF   mun  cobertura | veg. nativa ÷ natural (÷ cobertura)   r | consolidada ÷ agropecuária   r | sinais")
    for x in t.itertuples():
        print(f"{x.uf}  {x.municipios:4d}  {pct(x.cobertura_car)}    | "
              f"{pct(getattr(x, 'vn_razao', math.nan))} ({pct(getattr(x, 'vn_lida', math.nan))})"
              f"                 {num(getattr(x, 'vn_r', math.nan))} | "
              f"{pct(getattr(x, 'ac_lida', math.nan))}                    {num(getattr(x, 'ac_r', math.nan))} | "
              f"{x.sinais}")
    n = (t["sinais"] != "").sum()
    print(f"\n{n} UF(s) sinalizada(s) — razão fora de {FAIXA} ou correlação abaixo de {R_MIN}")


if __name__ == "__main__":
    main()
