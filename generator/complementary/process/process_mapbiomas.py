"""
process_mapbiomas.py — Uso e cobertura do solo por município (Etapa 2, §7.9–7.10).

Camada A (municipal): lê a planilha de estatísticas do MapBiomas
(data/raw/mapbiomas/mapbiomas_cobertura_municipios.xlsx) e produz a tabela longa
`mapbiomas_municipio` (cod_municipio, ano, classe_id, classe_nome, grupo_analitico,
area_ha, percentual_area_municipal, colecao, versao, data_download).

Mantém a classificação ORIGINAL (config/land_use_classes.csv só acrescenta um
grupo analítico; não apaga a classe original). O percentual usa a área municipal
de dim_municipio quando disponível (senão null).

Também gera a comparação municipal CAR × MapBiomas (§7.10) quando ambas existirem
— como comparação METODOLÓGICA (não erro automático de uma fonte).

Camada B (piloto por imóvel CAR): função car_land_use_pilot() apenas ESBOÇADA e
guardada — recorte de raster por imóvel exige rasterstats/GEE e relatório de
viabilidade antes de rodar nacionalmente. NÃO executa por padrão.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import (  # noqa: E402
    RAW_DIR, PROCESSED_DIR, CONFIG_DIR, cod_mun7, save_table, write_manifest, today_iso,
)


def _classes() -> pd.DataFrame:
    return pd.read_csv(CONFIG_DIR / "land_use_classes.csv", sep=";", dtype=str)


def _pick(cols, *keys):
    for c in cols:
        cl = str(c).lower()
        if all(k in cl for k in keys):
            return c
    return None


def _read_stats() -> tuple[pd.DataFrame, str]:
    """Lê a planilha oficial de Estatísticas do MapBiomas (Coverage). O export real
    (Coleção 10.1, testado nesta integração) tem várias abas — os dados ficam na
    aba que começa com "COVERAGE" (ex.: COVERAGE_10.1); as demais (READ_ME, PIVOT_*,
    METADADOS, LEGEND_CODE) são auxiliares. Formato wide: 1 linha por
    município×classe, colunas country/biome/state/state_acronym/municipality/
    class_id/class_level_0..4/<anos 1985..2024> — SEM coluna de código IBGE
    (resolvida por nome+UF em _resolver_cod_ibge)."""
    for name in ("mapbiomas_cobertura_municipios.xlsx", "mapbiomas_cobertura_municipios.csv"):
        p = RAW_DIR / "mapbiomas" / name
        if not p.exists():
            continue
        if p.suffix == ".csv":
            return pd.read_csv(p), name
        wb_sheets = pd.ExcelFile(p).sheet_names
        aba = next((s for s in wb_sheets if s.upper().startswith("COVERAGE")), wb_sheets[0])
        # SEM dtype=str: as colunas de ano já vêm como float nativo do Excel
        # (formato internacional, ponto=decimal) — forçar str e depois tentar
        # reparsear como pt-BR (ponto=milhar) corrompe os valores.
        return pd.read_excel(p, sheet_name=aba), f"{name}::{aba}"
    raise SystemExit("Planilha MapBiomas ausente. Rode download/download_mapbiomas.py primeiro.")


def _norm_nome(s) -> str:
    import unicodedata
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    return s.strip().upper()


def _resolver_cod_ibge(raw: pd.DataFrame, c_municipio: str, c_uf: str) -> tuple[dict, "pd.Series"]:
    """Join por (nome_municipio normalizado, sigla_uf) -> cod_ibge, usando
    data/raw/ibge/municipios.csv (mesma fonte de process_geography.py). Necessário
    porque a planilha de Estatísticas do MapBiomas não traz o código IBGE."""
    ref_path = RAW_DIR / "ibge" / "municipios.csv"
    if not ref_path.exists():
        raise SystemExit(f"Referência ausente: {ref_path} (rode download_ibge_geography.py)")
    ref = pd.read_csv(ref_path, sep=";", dtype=str)
    ref["_chave"] = ref["nome_municipio"].map(_norm_nome) + "|" + ref["sigla_uf"].str.upper()
    lookup = dict(zip(ref["_chave"], ref["cod_ibge"].map(cod_mun7)))

    chaves = raw[c_municipio].map(_norm_nome) + "|" + raw[c_uf].str.upper()
    return lookup, chaves


def build(colecao=None, versao=None) -> pd.DataFrame:
    raw, fonte_aba = _read_stats()
    cls = _classes()
    id2grp = dict(zip(cls["classe_id"], cls["grupo_analitico"]))
    id2nome = dict(zip(cls["classe_id"], cls["classe_nome"]))
    cols = list(raw.columns)

    c_cod = _pick(cols, "cod", "ibge") or _pick(cols, "geocod")
    c_municipio = _pick(cols, "municipality") or _pick(cols, "municipio")
    c_uf = _pick(cols, "state_acronym") or _pick(cols, "sigla", "uf") or _pick(cols, "acronym")
    c_class = _pick(cols, "class_id") or _pick(cols, "class", "id") or _pick(cols, "classe")
    # fallback de nome de classe quando class_id não bate com o config (ex.: coleção nova)
    c_class_nome = _pick(cols, "class_level_1") or _pick(cols, "class_level_0")
    anos = [c for c in cols if str(c).strip().isdigit() and len(str(c).strip()) == 4]

    cod_por_chave = None
    if not c_cod and c_municipio and c_uf:
        lookup, chaves = _resolver_cod_ibge(raw, c_municipio, c_uf)
        raw = raw.assign(_chave_join=chaves)
        cod_por_chave = lookup
        sem_match = sorted({k for k in chaves.unique() if k not in lookup or lookup.get(k) is None})
        if sem_match:
            print(f"  [AVISO] {len(sem_match)} combinação(ões) município+UF sem correspondência "
                  f"em data/raw/ibge/municipios.csv (amostra: {sem_match[:5]})")

    def _norm_id(x) -> str | None:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        s = str(x).strip()
        return s[:-2] if s.endswith(".0") else s

    def _to_area(val) -> float | None:
        """Valores de área já vêm como float nativo do Excel (formato
        internacional). Só reparseia texto pt-BR se, excepcionalmente, a
        célula vier como string (ex.: export diferente)."""
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        if isinstance(val, str):
            s = val.strip()
            if not s:
                return None
            s = s.replace(".", "").replace(",", ".") if ("," in s and s.rfind(",") > s.rfind(".")) else s
            try:
                return float(s)
            except ValueError:
                return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    rows = []
    if anos:  # formato wide: 1 linha por município×classe, colunas por ano
        for _, r in raw.iterrows():
            if c_cod:
                cod = cod_mun7(r[c_cod])
            elif cod_por_chave is not None:
                cod = cod_por_chave.get(r["_chave_join"])
            else:
                cod = None
            cid = _norm_id(r[c_class]) if c_class else None
            nome_classe = id2nome.get(cid) or (str(r[c_class_nome]).strip() if c_class_nome else None)
            grupo = id2grp.get(cid)
            for ano in anos:
                area = _to_area(r.get(ano))
                if area is None:
                    continue
                rows.append({"cod_municipio": cod, "ano": int(ano), "classe_id": cid,
                             "classe_nome": nome_classe, "grupo_analitico": grupo,
                             "area_ha": round(area, 4)})
    else:  # formato long
        c_ano = _pick(cols, "ano") or _pick(cols, "year")
        c_area = _pick(cols, "area")
        for _, r in raw.iterrows():
            if c_cod:
                cod = cod_mun7(r[c_cod])
            elif cod_por_chave is not None:
                cod = cod_por_chave.get(r["_chave_join"])
            else:
                cod = None
            cid = str(r[c_class]).strip() if c_class else None
            try:
                area = float(str(r[c_area]).replace(".", "").replace(",", "."))
            except (TypeError, ValueError):
                area = None
            rows.append({"cod_municipio": cod, "ano": int(r[c_ano]) if str(r.get(c_ano, "")).isdigit() else None,
                         "classe_id": cid, "classe_nome": id2nome.get(cid),
                         "grupo_analitico": id2grp.get(cid), "area_ha": round(area, 4) if area else None})

    df = pd.DataFrame(rows)
    rejeitados = int(df["cod_municipio"].isna().sum())
    if rejeitados:
        print(f"  [AVISO] {rejeitados:,} linha(s) sem cod_municipio resolvido — mantidas com null "
              "(não descartamos silenciosamente; ver amostra de combinações sem match acima)")
    # percentual sobre a área municipal (dim_municipio), quando disponível
    dimp = PROCESSED_DIR / "dimensions" / "dim_municipio.parquet"
    if dimp.exists():
        dim = pd.read_parquet(dimp)[["cod_municipio", "area_municipal_ha"]]
        df = df.merge(dim, on="cod_municipio", how="left")
        df["percentual_area_municipal"] = (df["area_ha"] / df["area_municipal_ha"] * 100).round(2)
        df = df.drop(columns="area_municipal_ha")
    else:
        df["percentual_area_municipal"] = None
    df["colecao"] = colecao
    df["versao"] = versao
    df["data_download"] = today_iso()
    df.attrs["fonte_aba"] = fonte_aba
    return df


def comparar_car_mapbiomas() -> pd.DataFrame:
    """Comparação municipal CAR × MapBiomas (§7.10). Metodológica, não 'erro'."""
    mbp = PROCESSED_DIR / "municipality" / "mapbiomas_municipio.parquet"
    carp = PROCESSED_DIR / "geospatial" / "car_municipio_summary.parquet"
    if not (mbp.exists() and carp.exists()):
        return pd.DataFrame()
    mb = pd.read_parquet(mbp)
    car = pd.read_parquet(carp)
    ano_max = mb["ano"].max()
    mb = mb[mb["ano"] == ano_max]
    agro = mb[mb["grupo_analitico"].isin(["agricultura", "pastagem", "agropecuaria", "silvicultura"])]
    veg = mb[mb["grupo_analitico"].isin(["formacao_florestal", "formacao_savanica", "formacao_campestre"])]
    ag = agro.groupby("cod_municipio")["area_ha"].sum().rename("area_agropecuaria_mapbiomas_ha")
    vg = veg.groupby("cod_municipio")["area_ha"].sum().rename("area_vegetacao_mapbiomas_ha")
    out = car[["cod_municipio", "area_geometrica_uniao_ha"]].merge(ag, on="cod_municipio", how="left")
    out = out.merge(vg, on="cod_municipio", how="left")
    out["ano_mapbiomas"] = ano_max
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--colecao")
    ap.add_argument("--versao")
    args = ap.parse_args()

    df = build(args.colecao, args.versao)
    outs = save_table(df, PROCESSED_DIR / "municipality" / "mapbiomas_municipio")
    cmp = comparar_car_mapbiomas()
    if not cmp.empty:
        outs += save_table(cmp, PROCESSED_DIR / "municipality" / "car_mapbiomas_comparacao")

    write_manifest("mapbiomas_municipio", source="MapBiomas — estatísticas municipais",
                   reference_date=None, source_files=[str(RAW_DIR / "mapbiomas")],
                   row_count=len(df), municipality_count=df["cod_municipio"].nunique(),
                   output_files=outs, extra={"colecao": args.colecao, "versao": args.versao})
    print(f"[MAPBIOMAS] {len(df):,} linhas · municípios={df['cod_municipio'].nunique():,}")


def car_land_use_pilot(uf: str):  # pragma: no cover
    """ESBOÇO (não executar nacionalmente). Recorta o raster MapBiomas por imóvel
    do CAR e calcula área por classe. Requer rasterstats + o GeoTIFF da coleção.
    Gerar relatório de tempo/memória/custo antes de escalar (briefing §7.9 B)."""
    raise NotImplementedError(
        "Piloto CAR×MapBiomas por imóvel: requer rasterstats/GEE e relatório de "
        "viabilidade. Ver docs/METHODOLOGY.md e docs/INTEGRATION_PLAN.md.")


if __name__ == "__main__":
    main()
