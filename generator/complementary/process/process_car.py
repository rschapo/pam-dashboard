"""
process_car.py — Pipeline geoespacial do CAR, incremental e por UF (Etapa 2, §7.3–7.8).

Trata as geometrias do SICAR de uma UF/município: padroniza CRS (armazenamento
EPSG:4674; área em EPSG:5880), corrige geometrias inválidas (make_valid/buffer(0),
documentado), calcula área geométrica e compara com a declarada, intersecta com a
malha municipal para atribuição e distribuição de área, mede sobreposições e
resume por município. Requer geopandas/shapely/pyogrio (instalar na sua máquina).

NÃO elimina registros inconsistentes: gera camada VÁLIDA e camada de REJEIÇÕES.
NÃO decide qual cadastro é o "dono" em caso de sobreposição.

Parâmetros (execução incremental — comece por 1 município, depois 1 UF):
  --uf MT                UF piloto (obrigatório salvo --input)
  --municipio 5107925    processa só um município (subconjunto)
  --input <path>         shapefile/gpkg específico (sobrepõe data/raw/car/<uf>/)
  --output <dir>         diretório de saída (default data/processed/geospatial/)
  --malha <path>         malha municipal (default data/raw/ibge/malha_municipios.gpkg)
  --sample N             amostra N imóveis (teste rápido)
  --force                reprocessa mesmo se a saída existir

Saídas (por UF):
  car_imoveis_validos_<UF>.parquet          (geometria + flags)
  car_imovel_municipio_intersection_<UF>.parquet
  car_municipio_summary.parquet             (acumulativo por UF)
  car_layer_availability.csv
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # p/ importar _stats via orquestrador
from common import (  # noqa: E402
    RAW_DIR, PROCESSED_DIR, CONFIG_DIR, CRS_STORAGE, CRS_AREA,
    cod_mun7, uf_from_cod, write_manifest,
)

DIVERG_PCT_ALERTA = 20.0


def _require_geo():
    try:
        import geopandas  # noqa: F401
        import shapely  # noqa: F401
    except ImportError:
        raise SystemExit(
            "geopandas/shapely ausentes. Instale na sua máquina:\n"
            "  pip install geopandas shapely pyogrio pyproj\n"
            "O tratamento geométrico do CAR não roda sem eles."
        )


def _hash(x) -> str:
    return hashlib.sha256(f"CAR::{x}".encode()).hexdigest()[:24]


def _status_map() -> dict:
    m = pd.read_csv(CONFIG_DIR / "car_status_map.csv", sep=";", dtype=str, keep_default_na=False)
    return {r["status_original"].strip(): r["status_padronizado"] for _, r in m.iterrows()}


def _load_car(uf: str, input_path: str | None, sample: int | None):
    import geopandas as gpd
    if input_path:
        gdf = gpd.read_file(input_path)
    else:
        d = RAW_DIR / "car" / uf
        imv = d / "imoveis"                       # camada núcleo = perímetros dos imóveis
        search = imv if imv.exists() else d
        files = (sorted(search.rglob("*.shp")) + sorted(search.rglob("*.gpkg"))
                 + sorted(search.rglob("*.geojson")) + sorted(search.rglob("*.json")))
        if not imv.exists():                      # sem subpasta: pega só a camada de imóvel
            pref = [f for f in files if re.search(r"imovel|perimetr", f.name, re.I)]
            files = pref or files
        if not files:
            raise SystemExit(f"Sem shapefiles do CAR (imóveis) em {d}. Rode download_car.py e coloque os arquivos.")
        parts = [gpd.read_file(f) for f in files]
        gdf = pd.concat(parts, ignore_index=True)
        gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=parts[0].crs)
    if sample:
        gdf = gdf.iloc[:sample].copy()
    return gdf


def _fix_geometry(gdf):
    from shapely import make_valid
    if gdf.crs is None:
        gdf.set_crs(CRS_STORAGE, inplace=True)
    gdf = gdf.to_crs(CRS_STORAGE)
    invalid = ~gdf.geometry.is_valid
    if invalid.any():
        gdf.loc[invalid, "geometry"] = gdf.loc[invalid, "geometry"].apply(
            lambda g: make_valid(g) if g is not None else g)
        still = ~gdf.geometry.is_valid
        if still.any():
            gdf.loc[still, "geometry"] = gdf.loc[still, "geometry"].buffer(0)
    return gdf, int(invalid.sum())


def _pick(cols, *keys):
    for c in cols:
        cl = str(c).lower()
        if all(k in cl for k in keys):
            return c
    return None


def process_uf(uf, input_path, out_dir, malha_path, sample, force):
    _require_geo()
    import geopandas as gpd

    out_dir = Path(out_dir or (PROCESSED_DIR / "geospatial"))
    out_dir.mkdir(parents=True, exist_ok=True)
    val_path = out_dir / f"car_imoveis_validos_{uf}.parquet"
    if val_path.exists() and not force:
        print(f"[CAR/{uf}] saída já existe (use --force). Pulando.")
        return

    gdf = _load_car(uf, input_path, sample)
    cols = list(gdf.columns)
    # Esquema SICAR (AREA_IMOVEL): cod_imovel, num_area, mod_fiscal, ind_status,
    # des_condic, municipio, cod_estado, dat_criaca, dat_atuali.
    c_id = _pick(cols, "cod_imovel") or _pick(cols, "cod", "car") or _pick(cols, "id")
    c_mun = _pick(cols, "municipio", "cod") or _pick(cols, "cod", "ibge")
    c_areadecl = _pick(cols, "num_area") or _pick(cols, "area", "declar") or _pick(cols, "area")
    c_status = _pick(cols, "ind_status") or _pick(cols, "situacao") or _pick(cols, "status")
    c_dt_ins = _pick(cols, "dat_criac") or _pick(cols, "data", "inscri")
    c_dt_atu = _pick(cols, "dat_atuali") or _pick(cols, "data", "atualiz")
    c_mod = _pick(cols, "mod_fiscal") or _pick(cols, "m_fiscal") or _pick(cols, "fiscal")

    def _mun_from_carid(v):  # SICAR embute o código IBGE no cod_imovel: UF-<7díg>-<hash>
        m = re.search(r"-(\d{7})-", str(v))
        return cod_mun7(m.group(1)) if m else None

    gdf, n_invalid = _fix_geometry(gdf)
    gdf["area_geometrica_ha"] = gdf.to_crs(CRS_AREA).geometry.area / 10_000.0

    if c_mun:
        cod_decl = list(gdf[c_mun].map(cod_mun7))
    elif c_id:
        cod_decl = list(gdf[c_id].map(_mun_from_carid))
    else:
        cod_decl = [None] * len(gdf)

    status_map = _status_map()
    rec = pd.DataFrame({
        "id_car_hash": gdf[c_id].map(_hash) if c_id else [None] * len(gdf),
        "uf_origem": uf,
        "cod_municipio_declarado": cod_decl,
        "area_declarada_ha": pd.to_numeric(gdf[c_areadecl], errors="coerce") if c_areadecl else None,
        "area_geometrica_ha": gdf["area_geometrica_ha"].round(4),
        "modulos_fiscais_declarado": pd.to_numeric(gdf[c_mod], errors="coerce") if c_mod else None,
        "situacao_car_original": gdf[c_status] if c_status else None,
        "situacao_car_padronizada": (gdf[c_status].map(lambda s: status_map.get(str(s).strip()))
                                     if c_status else None),
        "data_inscricao": gdf[c_dt_ins] if c_dt_ins else None,
        "data_atualizacao": gdf[c_dt_atu] if c_dt_atu else None,
    })
    ad = pd.to_numeric(rec["area_declarada_ha"], errors="coerce")
    # denominador 0 -> NaN (evita divisão por zero). pd.to_numeric normaliza pd.NA -> np.nan
    # em float64, senão .round() quebra no pandas 3.x (NAType não define __round__).
    _dif = (rec["area_geometrica_ha"] - ad).abs() / ad.replace(0, float("nan")) * 100
    rec["diferenca_area_percentual"] = pd.to_numeric(_dif, errors="coerce").round(2)
    rec["flag_geometria_invalida"] = False
    rec["flag_area_divergente"] = rec["diferenca_area_percentual"] > DIVERG_PCT_ALERTA
    rec["flag_fora_uf"] = rec["cod_municipio_declarado"].map(lambda c: (uf_from_cod(c) != uf) if c else True)
    rec["flag_duplicidade"] = rec["id_car_hash"].duplicated(keep=False)

    gval = gpd.GeoDataFrame(rec, geometry=gdf.geometry.values, crs=CRS_STORAGE)
    gval.to_parquet(val_path)

    # Interseção com malha municipal (§7.4)
    inter = _intersect_municipios(gval, malha_path, uf)
    inter_path = out_dir / f"car_imovel_municipio_intersection_{uf}.parquet"
    if inter is not None:
        inter.to_parquet(inter_path, index=False)

    # Resumo municipal + sobreposições (§7.5, §7.7)
    summ = _municipio_summary(gval, inter)
    _append_summary(summ, out_dir / "car_municipio_summary.parquet")

    # Disponibilidade de camadas ambientais (§7.6)
    _layer_availability(uf, cols, out_dir)

    write_manifest(f"car_{uf}", source="SICAR — CAR", reference_date=None,
                   row_count=len(gval), municipality_count=(inter["cod_municipio"].nunique() if inter is not None else 0),
                   warnings=[f"geometrias corrigidas: {n_invalid}",
                             f"fora da UF: {int(rec['flag_fora_uf'].sum())}",
                             f"área divergente>{DIVERG_PCT_ALERTA}%: {int(rec['flag_area_divergente'].sum())}"],
                   output_files=[str(val_path), str(inter_path)])
    print(f"[CAR/{uf}] {len(gval):,} imóveis · inválidas corrigidas {n_invalid} · "
          f"fora UF {int(rec['flag_fora_uf'].sum())}")


def _to_multipoly(geom):
    """Coage a geometria à sua parte poligonal como MultiPolygon (ou None se não houver).
    make_valid/buffer(0) podem produzir GeometryCollection; o gpd.overlay rejeita tipos
    mistos ('df contains mixed geometry types'). Homogeneizar em MultiPolygon resolve."""
    from shapely.geometry import Polygon, MultiPolygon, GeometryCollection
    from shapely.ops import unary_union
    if geom is None or geom.is_empty:
        return None
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    if isinstance(geom, MultiPolygon):
        return geom
    if isinstance(geom, GeometryCollection):
        polys = [g for g in geom.geoms if isinstance(g, (Polygon, MultiPolygon)) and not g.is_empty]
        if not polys:
            return None
        u = unary_union(polys)
        return u if isinstance(u, MultiPolygon) else MultiPolygon([u])
    return None


def _intersect_municipios(gval, malha_path, uf):
    import geopandas as gpd
    malha_path = Path(malha_path or (RAW_DIR / "ibge" / "malha_municipios.gpkg"))
    if not malha_path.exists():
        print(f"  [AVISO] malha municipal ausente ({malha_path}); interseção pulada. "
              "Rode download_ibge_geography.py --malha.")
        return None
    malha = gpd.read_file(malha_path).to_crs(CRS_STORAGE)
    cod_col = _pick(list(malha.columns), "cod") or _pick(list(malha.columns), "cd_mun") or "codarea"
    malha = malha.rename(columns={cod_col: "cod_municipio"})
    malha["cod_municipio"] = malha["cod_municipio"].map(cod_mun7)
    malha["geometry"] = malha.geometry.map(_to_multipoly)
    malha = gpd.GeoDataFrame(malha[malha.geometry.notna()], geometry="geometry", crs=CRS_STORAGE)
    # gval pode conter tipos mistos (Polygon/MultiPolygon/GeometryCollection após make_valid);
    # o overlay exige tipo homogêneo -> coage a MultiPolygon (parte poligonal).
    g_in = gval[["id_car_hash", "geometry"]].copy()
    g_in["geometry"] = g_in.geometry.map(_to_multipoly)
    g_in = gpd.GeoDataFrame(g_in[g_in.geometry.notna()], geometry="geometry", crs=gval.crs)
    inter = gpd.overlay(g_in, malha[["cod_municipio", "geometry"]],
                        how="intersection", keep_geom_type=False)
    inter["area_intersecao_ha"] = inter.to_crs(CRS_AREA).geometry.area / 10_000.0
    tot = inter.groupby("id_car_hash")["area_intersecao_ha"].transform("sum")
    inter["percentual_area_imovel"] = (inter["area_intersecao_ha"] / tot * 100).round(2)
    idxmax = inter.groupby("id_car_hash")["area_intersecao_ha"].transform("max")
    inter["municipio_principal"] = inter["area_intersecao_ha"] >= idxmax
    return pd.DataFrame(inter.drop(columns="geometry"))


def _safe_union_ha(geoms):
    """Área da união (ha) robusta a topologia inválida: union_all direto; se falhar,
    make_valid; por fim buffer(0). Retorna None só se tudo falhar. geoms em EPSG:5880."""
    from shapely import make_valid
    for tentativa in ("direto", "make_valid", "buffer0"):
        try:
            g = geoms
            if tentativa == "make_valid":
                g = geoms.apply(lambda x: make_valid(x) if x is not None else x)
            elif tentativa == "buffer0":
                g = geoms.buffer(0)
            u = g.union_all()
            if u is not None and not u.is_empty:
                return round(u.area / 10_000.0, 4)
        except Exception:
            continue
    return None


def _municipio_summary(gval, inter):
    import geopandas as gpd
    from _stats import resumo_area
    if inter is None:
        # sem malha: atribui pelo município declarado (documentar a limitação)
        base = gval.copy()
        base["cod_municipio"] = base["cod_municipio_declarado"]
        grouped = base
    else:
        principal = inter[inter["municipio_principal"]][["id_car_hash", "cod_municipio"]]
        grouped = gval.merge(principal, on="id_car_hash", how="left")

    rows = []
    for cod, g in grouped.groupby("cod_municipio"):
        if cod is None:
            continue
        gg = gpd.GeoDataFrame(g, geometry="geometry", crs=CRS_STORAGE).to_crs(CRS_AREA)
        area_bruta = float(g["area_geometrica_ha"].sum())
        union_area = _safe_union_ha(gg.geometry)
        sobre = (area_bruta - union_area) if union_area is not None else None
        pct_sobre = (100.0 * sobre / area_bruta) if (sobre is not None and area_bruta) else None
        rows.append({
            "cod_municipio": cod,
            "quantidade_cadastros": len(g),
            "quantidade_cadastros_validos": int((~g["flag_area_divergente"]).sum()),
            "area_declarada_total_ha": round(float(pd.to_numeric(g["area_declarada_ha"], errors="coerce").sum()), 4),
            "area_geometrica_bruta_ha": round(area_bruta, 4),
            "area_geometrica_uniao_ha": round(union_area, 4) if union_area is not None else None,
            "area_sobreposta_ha": round(sobre, 4) if sobre is not None else None,
            "percentual_sobreposicao": round(pct_sobre, 2) if pct_sobre is not None else None,
            "nivel_sobreposicao": _nivel_sobre(pct_sobre),
            **{k: v for k, v in resumo_area(g["area_geometrica_ha"]).items()
               if k in ("area_media_ha", "area_mediana_ha", "area_p25_ha", "area_p75_ha")},
            "data_referencia": None,
        })
    return pd.DataFrame(rows)


def _nivel_sobre(pct):
    if pct is None:
        return None
    if pct <= 1:
        return "sem_sobreposicao_relevante"
    if pct <= 5:
        return "mais_1_ate_5_percentual"
    if pct <= 20:
        return "mais_5_ate_20_percentual"
    return "mais_20_percentual"


def _append_summary(new_df, path):
    if new_df.empty:
        return
    if path.exists():
        old = pd.read_parquet(path)
        old = old[~old["cod_municipio"].isin(new_df["cod_municipio"])]
        new_df = pd.concat([old, new_df], ignore_index=True)
    new_df.sort_values("cod_municipio").to_parquet(path, index=False)
    new_df.to_csv(path.with_suffix(".csv"), sep=";", index=False, encoding="utf-8")


def _layer_availability(uf, cols, out_dir):
    camadas = {"area_imovel": ["area", "imovel"], "area_consolidada": ["consolidad"],
               "vegetacao_nativa": ["remanescente", "vegeta"], "reserva_legal": ["reserva"],
               "app": ["app", "preserva"], "uso_restrito": ["restrito"], "pousio": ["pousio"]}
    rows = []
    lc = [str(c).lower() for c in cols]
    for camada, keys in camadas.items():
        disp = any(any(k in c for c in lc) for k in keys)
        rows.append({"uf": uf, "camada": camada, "disponivel": disp,
                     "fonte": "SICAR", "data_referencia": None,
                     "qualidade_avaliada": None, "observacao": None})
    path = out_dir / "car_layer_availability.csv"
    df = pd.DataFrame(rows)
    if path.exists():
        old = pd.read_csv(path, sep=";")
        df = pd.concat([old[old["uf"] != uf], df], ignore_index=True)
    df.to_csv(path, sep=";", index=False, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Pipeline geoespacial do CAR (por UF)")
    ap.add_argument("--uf")
    ap.add_argument("--municipio")
    ap.add_argument("--input")
    ap.add_argument("--output")
    ap.add_argument("--malha")
    ap.add_argument("--sample", type=int)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if not args.uf and not args.input:
        raise SystemExit("Informe --uf (piloto) ou --input.")
    process_uf(args.uf, args.input, args.output, args.malha, args.sample, args.force)


if __name__ == "__main__":
    main()
