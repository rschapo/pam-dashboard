"""
export_uso_solo.py — gera public/data/mapbiomas_mun.json (aba Uso do Solo).

Lê mapbiomas_municipio (process_mapbiomas.py), fica com o ano mais recente e soma,
por município, a área (ha) dos grupos analíticos nas chaves que o front usa:
  natural  formação florestal, savânica e campestre, área úmida e outras formações
  agri     agricultura           past   pastagem            silv   silvicultura
  mosaic   mosaico de usos       urban  área urbanizada     agua   corpo d'água
  outros   área não vegetada e as classes que o config não agrupa (usina
           fotovoltaica, não observado)
Área com uma casa decimal; o que arredonda a zero fica fora.

Só entram municípios da dim_municipio: nenhuma chave vazia chega ao painel. As
lagoas dos Patos e Mirim (RS), áreas fora de município no IBGE, vão para
"fora_de_municipio" e não entram nos totais, que o front soma a partir dos
municípios. As linhas sem código (fragmentos de borda que a planilha rotula com a
UF vizinha, cerca de 70 ha) ficam de fora, com aviso. Fernando de Noronha não tem
linha na planilha: o MapBiomas não cobre o arquipélago.

Nada aqui depende de rede.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PROCESSED_DIR, now_iso  # noqa: E402
from process_mapbiomas import AREAS_FORA_DE_MUNICIPIO  # noqa: E402

PUBLIC_DATA = Path(__file__).resolve().parents[3] / "public" / "data"

CHAVE_POR_GRUPO = {
    "formacao_florestal": "natural", "formacao_savanica": "natural",
    "formacao_campestre": "natural", "area_umida": "natural",
    "outras_formacoes_naturais": "natural",
    "agricultura": "agri", "pastagem": "past", "silvicultura": "silv",
    "mosaico_de_usos": "mosaic", "area_urbana": "urban", "corpo_dagua": "agua",
    "area_nao_vegetada": "outros",
}


def _areas(grupos: pd.Series) -> dict:
    """{chave: ha} de um código, sem as chaves que arredondam a zero."""
    return {k: round(v, 1) for k, v in grupos.items() if round(v, 1) != 0}


def build_uso_solo() -> dict:
    p = PROCESSED_DIR / "municipality" / "mapbiomas_municipio.parquet"
    if not p.exists():
        raise SystemExit(f"{p.name} ausente em {p.parent}. Rode process_mapbiomas.py.")
    mb = pd.read_parquet(p, columns=["cod_municipio", "ano", "grupo_analitico", "area_ha", "colecao"])
    ano = int(mb["ano"].max())
    cur = mb[mb["ano"] == ano].copy()
    cur["chave"] = cur["grupo_analitico"].map(CHAVE_POR_GRUPO).fillna("outros")

    sem_cod = cur["cod_municipio"].isna()
    if sem_cod.any():
        print(f"  [AVISO] {cur.loc[sem_cod, 'area_ha'].sum():,.1f} ha sem município em {ano} "
              "(fragmentos de borda da planilha) ficam de fora")
    piv = cur[~sem_cod].groupby(["cod_municipio", "chave"])["area_ha"].sum()

    dim = set(pd.read_parquet(PROCESSED_DIR / "dimensions" / "dim_municipio.parquet",
                              columns=["cod_municipio"])["cod_municipio"])
    mun, fora = {}, {}
    for cod, grupos in piv.groupby(level=0):
        areas = _areas(grupos.droplevel(0))
        if cod in dim:
            if areas:
                mun[cod] = areas
        elif cod in AREAS_FORA_DE_MUNICIPIO:
            nome, uf = AREAS_FORA_DE_MUNICIPIO[cod]
            fora[cod] = {"nome": nome, "uf": uf, **areas}
        else:
            raise SystemExit(f"Código {cod} não é município nem área conhecida fora de município.")

    colecao = cur["colecao"].dropna()
    return {
        "ano": ano,
        "colecao": colecao.iloc[0] if len(colecao) else None,
        "fonte": "MapBiomas, estatísticas de cobertura por município",
        "gerado_em": now_iso(),
        "fora_de_municipio": fora,
        "mun": mun,
    }


def main():
    obj = build_uso_solo()
    PUBLIC_DATA.mkdir(parents=True, exist_ok=True)
    p = PUBLIC_DATA / "mapbiomas_mun.json"
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    mb = p.stat().st_size / 1_048_576
    print(f"  mapbiomas_mun.json: {len(obj['mun']):,} municípios · {obj['ano']} · "
          f"Coleção {obj['colecao']} · {mb:.2f} MB · fora de município: {sorted(obj['fora_de_municipio'])}")


if __name__ == "__main__":
    main()
