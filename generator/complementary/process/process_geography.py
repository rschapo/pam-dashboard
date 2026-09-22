"""
process_geography.py — Dimensão territorial oficial `dim_municipio` (Etapa 1, §6.1).

Constrói a dimensão de municípios com a hierarquia geográfica completa do IBGE
(micro/meso, regiões geográficas imediata/intermediária, UF, grande região).

Fontes de entrada (em ordem de preferência):
  1. data/raw/ibge/municipios.csv          (coletado por download_ibge_geography.py)
  2. data/raw/ibge/ibge_municipios_full.csv (fallback offline da base-mestra — mesmo layout)
Área territorial (opcional, se presente):
  data/raw/ibge/areas_municipios.xlsx      (IBGE Áreas Territoriais)
Indicador "sem produção" (opcional; presença apenas, NÃO junção de dados):
  public/data/pkg.json  (PAM) e public/data/ppm.json (PPM) — chaves de mun_data.

Saídas:
  data/processed/dimensions/dim_municipio.parquet | .csv
  data/processed/dimensions/dim_municipio_codigos_historicos.csv  (correspondência)
  data/manifests/dim_municipio.json

Regras (§6.1): preserva micro/meso; inclui regiões imediata/intermediária; usa a
malha mais recente disponível; NÃO exclui municípios sem PAM/PPM (marca indicador);
área em hectares; ausência = null (nunca zero).

Uso:
  python process_geography.py [--ano-malha 2024] \
      [--pam-json ../../public/data/pkg.json] [--ppm-json ../../public/data/ppm.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import (  # noqa: E402
    RAW_DIR, PROCESSED_DIR, CONFIG_DIR, PROJECT_ROOT,
    cod_mun7, UF_NAMES, REGION_NAME2COD, IBGE2UF, UF_REGION_NAME,
    save_table, write_manifest,
)


def _v(x):
    """Normaliza célula: NaN/''/'nan' → None (evita o gotcha de NaN ser 'truthy')."""
    if x is None:
        return None
    s = str(x).strip()
    return None if s in ("", "nan", "None", "NaN") else x

DIM_COLUMNS = [
    "cod_municipio", "nome_municipio", "uf", "nome_uf",
    "cod_regiao", "nome_regiao",
    "cod_microrregiao", "nome_microrregiao",
    "cod_mesorregiao", "nome_mesorregiao",
    "cod_regiao_imediata", "nome_regiao_imediata",
    "cod_regiao_intermediaria", "nome_regiao_intermediaria",
    "area_municipal_ha", "ano_malha_referencia", "situacao_codigo",
    "flag_sem_producao_pam", "flag_sem_producao_ppm",
]


def _read_municipios_source() -> tuple[pd.DataFrame, str]:
    for name in ("municipios.csv", "ibge_municipios_full.csv"):
        p = RAW_DIR / "ibge" / name
        if p.exists():
            df = pd.read_csv(p, sep=";", dtype=str, keep_default_na=False, na_values=[""])
            return df, name
    raise SystemExit(
        "Nenhuma fonte de municípios encontrada em data/raw/ibge/.\n"
        "Rode download/download_ibge_geography.py (na sua máquina) ou copie o\n"
        "ibge_municipios_full.csv da base-mestra para data/raw/ibge/."
    )


def _read_estados() -> pd.DataFrame:
    p = RAW_DIR / "ibge" / "estados.csv"
    if p.exists():
        return pd.read_csv(p, sep=";", dtype=str, keep_default_na=False, na_values=[""])
    return pd.DataFrame(columns=["sigla_uf", "nome_uf", "cod_regiao"])


def _read_areas_ha() -> dict[str, float]:
    """Lê IBGE Áreas Territoriais. Preferência: areas_municipios.csv normalizado
    (cod_ibge;area_km2) gerado por download_ibge_areas.py; senão a planilha xlsx.
    Converte km²→ha. Ausente ⇒ {} (área = null, nunca zero)."""
    csvp = RAW_DIR / "ibge" / "areas_municipios.csv"
    if csvp.exists():
        d = pd.read_csv(csvp, sep=";", dtype={"cod_ibge": str})
        out = {}
        for _, r in d.iterrows():
            c = cod_mun7(r.get("cod_ibge"))
            km2 = pd.to_numeric(r.get("area_km2"), errors="coerce")
            if c and pd.notna(km2):
                out[c] = round(float(km2) * 100.0, 4)
        return out
    p = RAW_DIR / "ibge" / "areas_municipios.xlsx"
    if not p.exists():
        return {}
    try:
        raw = pd.read_excel(p, dtype=str)
    except Exception as e:  # pragma: no cover
        print(f"  [AVISO] não foi possível ler {p.name}: {e}")
        return {}
    cod_col = next((c for c in raw.columns if "CD_MUN" in c.upper() or "COD" in c.upper()), None)
    area_col = next((c for c in raw.columns if "AR_MUN" in c.upper() or "AREA" in c.upper()), None)
    if not cod_col or not area_col:
        print(f"  [AVISO] {p.name}: colunas de código/área não reconhecidas — área ficará null")
        return {}
    out = {}
    for _, r in raw.iterrows():
        c = cod_mun7(r[cod_col])
        try:
            km2 = float(str(r[area_col]).replace(".", "").replace(",", "."))
        except (TypeError, ValueError):
            km2 = None
        if c and km2 is not None:
            out[c] = round(km2 * 100.0, 4)  # km² → ha
    return out


def _mun_data_keys(json_path: Path | None) -> set[str]:
    if not json_path or not Path(json_path).exists():
        return set()
    try:
        doc = json.loads(Path(json_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {cod_mun7(k) for k in doc.get("mun_data", {}).keys() if cod_mun7(k)}


def build(ano_malha: int | None, pam_json: Path | None, ppm_json: Path | None) -> pd.DataFrame:
    src, src_name = _read_municipios_source()
    est = _read_estados()
    areas = _read_areas_ha()
    pam_keys = _mun_data_keys(pam_json)
    ppm_keys = _mun_data_keys(ppm_json)

    nome_uf_map = dict(zip(est.get("sigla_uf", []), est.get("nome_uf", []))) if len(est) else {}
    cod_regiao_map = dict(zip(est.get("sigla_uf", []), est.get("cod_regiao", []))) if len(est) else {}

    rows = []
    for _, r in src.iterrows():
        cod = cod_mun7(r.get("cod_ibge"))
        if not cod:
            continue
        uf = _v(r.get("sigla_uf")) or IBGE2UF.get(cod[:2])
        regiao_nome = _v(r.get("regiao")) or UF_REGION_NAME.get(uf)
        rows.append({
            "cod_municipio": cod,
            "nome_municipio": _v(r.get("nome_municipio")),
            "uf": uf,
            "nome_uf": nome_uf_map.get(uf) or UF_NAMES.get(uf),
            "cod_regiao": cod_regiao_map.get(uf) or REGION_NAME2COD.get(regiao_nome),
            "nome_regiao": regiao_nome,
            "cod_microrregiao": _v(r.get("cod_microrregiao")),
            "nome_microrregiao": _v(r.get("nome_microrregiao")),
            "cod_mesorregiao": _v(r.get("cod_mesorregiao")),
            "nome_mesorregiao": _v(r.get("nome_mesorregiao")),
            "cod_regiao_imediata": _v(r.get("cod_regiao_imediata")),
            "nome_regiao_imediata": _v(r.get("nome_regiao_imediata")),
            "cod_regiao_intermediaria": _v(r.get("cod_regiao_intermediaria")),
            "nome_regiao_intermediaria": _v(r.get("nome_regiao_intermediaria")),
            "area_municipal_ha": areas.get(cod),  # None se fonte de área ausente
            "ano_malha_referencia": ano_malha,
            "situacao_codigo": 0,  # 0 = município instalado/ativo
            "flag_sem_producao_pam": (cod not in pam_keys) if pam_keys else None,
            "flag_sem_producao_ppm": (cod not in ppm_keys) if ppm_keys else None,
        })

    df = pd.DataFrame(rows, columns=DIM_COLUMNS)
    df = df.drop_duplicates("cod_municipio").sort_values("cod_municipio").reset_index(drop=True)
    return df, src_name, len(areas), bool(pam_keys), bool(ppm_keys)


def build_code_history() -> pd.DataFrame:
    """Tabela de correspondência entre códigos históricos e atuais (§6.1).
    Populada a partir de config/municipio_code_history.csv se existir; caso
    contrário, cria a estrutura vazia (extensível). NÃO inventamos correspondências."""
    cols = ["cod_municipio_antigo", "cod_municipio_atual", "nome", "uf",
            "ano_alteracao", "tipo_alteracao", "fonte", "observacao"]
    cfg = CONFIG_DIR / "municipio_code_history.csv"
    if cfg.exists():
        return pd.read_csv(cfg, sep=";", dtype=str, keep_default_na=False)
    return pd.DataFrame(columns=cols)


def main():
    ap = argparse.ArgumentParser(description="Constrói dim_municipio (Etapa 1)")
    ap.add_argument("--ano-malha", type=int, default=2024,
                    help="Ano de referência da malha (rótulo declarado)")
    ap.add_argument("--pam-json", type=Path,
                    default=PROJECT_ROOT / "public" / "data" / "pkg.json")
    ap.add_argument("--ppm-json", type=Path,
                    default=PROJECT_ROOT / "public" / "data" / "ppm.json")
    args = ap.parse_args()

    print("Construindo dim_municipio …")
    df, src_name, n_areas, has_pam, has_ppm = build(args.ano_malha, args.pam_json, args.ppm_json)
    outdir = PROCESSED_DIR / "dimensions"
    outs = save_table(df, outdir / "dim_municipio")

    hist = build_code_history()
    hist_path = outdir / "dim_municipio_codigos_historicos.csv"
    hist_path.parent.mkdir(parents=True, exist_ok=True)
    hist.to_csv(hist_path, sep=";", index=False, encoding="utf-8")
    outs.append(str(hist_path))

    warnings = []
    if n_areas == 0:
        warnings.append("area_municipal_ha = null p/ todos: IBGE Áreas Territoriais não presente em data/raw/ibge/areas_municipios.xlsx")
    if not has_pam:
        warnings.append("flag_sem_producao_pam = null: pkg.json não encontrado no caminho informado")
    if not has_ppm:
        warnings.append("flag_sem_producao_ppm = null: ppm.json não encontrado no caminho informado")

    write_manifest(
        "dim_municipio",
        source=f"IBGE (malha/localidades) — entrada: {src_name}",
        reference_date=f"{args.ano_malha}-01-01",
        source_files=[str(RAW_DIR / "ibge" / src_name)],
        row_count=len(df),
        municipality_count=df["cod_municipio"].nunique(),
        rejected_rows=0,
        warnings=warnings,
        output_files=outs,
        extra={"areas_preenchidas": n_areas,
               "produtores_pam_marcados": bool(has_pam),
               "produtores_ppm_marcados": bool(has_ppm)},
    )

    print(f"  Municípios: {len(df):,}")
    print(f"  Com área preenchida: {n_areas:,} (demais = null)")
    print(f"  Saídas: {', '.join(Path(o).name for o in outs)}")
    for w in warnings:
        print(f"  [AVISO] {w}")


if __name__ == "__main__":
    main()
