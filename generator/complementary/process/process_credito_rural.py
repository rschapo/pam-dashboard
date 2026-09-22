"""
process_credito_rural.py — Constrói mun_credito_rural a partir dos JSONs brutos
gravados por download_credito_rural.py (data/raw/bcb/sicor_<finalidade>_<ano>.json).

Migrado de Base_Municipios_Brasil/scripts/coletar_base.py::coletar_credito_rural,
com uma correção: o recurso "Investimento" do SICOR não tem `codIbge` (só
`cdMunicipio` interno do BCB + nome + `cdEstado`) — por isso a coleta antiga
sempre vinha vazia para Investimento. Aqui resolvemos cod_ibge por
nome_municipio + UF (cdEstado traduzido via sicor_regiaouf_lookup.json),
mesma técnica usada em process_mapbiomas.py.

Saída: data/processed/municipality/credito_rural.parquet | .csv
Uso: python process_credito_rural.py [--ano-credito 2024]
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import RAW_DIR, PROCESSED_DIR, cod_mun7, save_table, write_manifest  # noqa: E402


def _norm_nome(s) -> str:
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    return s.strip().upper()


def _cdestado_para_uf() -> dict[str, str]:
    p = RAW_DIR / "bcb" / "sicor_regiaouf_lookup.json"
    if not p.exists():
        return {}
    registros = json.loads(p.read_text(encoding="utf-8")).get("value", [])
    return {str(r["cdEstado"]): r["nomeUF"] for r in registros if r.get("cdEstado") and r.get("nomeUF")}


def _nome_uf_para_cod_ibge() -> dict[str, str]:
    ref_path = RAW_DIR / "ibge" / "municipios.csv"
    if not ref_path.exists():
        return {}
    ref = pd.read_csv(ref_path, sep=";", dtype=str)
    chave = ref["nome_municipio"].map(_norm_nome) + "|" + ref["sigla_uf"].str.upper()
    return dict(zip(chave, ref["cod_ibge"].map(cod_mun7)))


def build(ano_credito: int) -> pd.DataFrame:
    cdestado2uf = _cdestado_para_uf()
    nomeuf2cod = _nome_uf_para_cod_ibge()

    partes = []
    for finalidade in ("custeio", "investimento"):
        p = RAW_DIR / "bcb" / f"sicor_{finalidade}_{ano_credito}.json"
        if not p.exists():
            print(f"  [AVISO] não encontrado: {p.name} — rode download_credito_rural.py")
            continue
        registros = json.loads(p.read_text(encoding="utf-8")).get("value", [])
        if not registros:
            continue
        d = pd.DataFrame(registros)
        vl = next((c for c in d.columns if c.lower().startswith("vl")), None)
        area = next((c for c in d.columns if c.lower().startswith("area") or c.lower().startswith("ar")), None)
        if not vl:
            print(f"  [AVISO] {finalidade}: campo de valor não identificado")
            continue

        c_cod_ibge = next((c for c in d.columns if c.lower() == "codibge"), None)
        if c_cod_ibge:
            d["cod_ibge"] = d[c_cod_ibge].map(cod_mun7)
        else:
            c_mun = next((c for c in d.columns if c.lower() == "municipio"), None)
            c_est = next((c for c in d.columns if c.lower() == "cdestado"), None)
            if not (c_mun and c_est and cdestado2uf):
                print(f"  [AVISO] {finalidade}: sem codIbge e sem nome+UF para resolver — pulando")
                continue
            uf = d[c_est].astype(str).map(cdestado2uf)
            chave = d[c_mun].map(_norm_nome) + "|" + uf.str.upper()
            d["cod_ibge"] = chave.map(nomeuf2cod)
            sem_match = int(d["cod_ibge"].isna().sum())
            if sem_match:
                print(f"  [AVISO] {finalidade}: {sem_match:,}/{len(d):,} linhas sem cod_ibge resolvido "
                      "(nome+UF sem correspondência)")

        d[vl] = pd.to_numeric(d[vl], errors="coerce")
        agg = {vl: "sum"}
        if area and area in d.columns:
            d[area] = pd.to_numeric(d[area], errors="coerce")
            agg[area] = "sum"
        g = d.dropna(subset=["cod_ibge"]).groupby("cod_ibge", as_index=False).agg(agg)
        g = g.rename(columns={vl: "valor_contratado", area: "area_ha"} if area else {vl: "valor_contratado"})
        g["ano_ref"] = ano_credito
        g["finalidade"] = finalidade.capitalize()
        g["fonte"] = "BCB/SICOR (MDCR)"
        if "area_ha" not in g:
            g["area_ha"] = None
        partes.append(g)

    if not partes:
        return pd.DataFrame()
    return pd.concat(partes, ignore_index=True).sort_values(["cod_ibge", "finalidade"]).reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser(description="Constrói mun_credito_rural (BCB/SICOR)")
    ap.add_argument("--ano-credito", type=int, default=2024)
    args = ap.parse_args()

    df = build(args.ano_credito)
    if df.empty:
        print("Nada a gravar — rode download_credito_rural.py antes.")
        return

    outdir = PROCESSED_DIR / "municipality"
    outs = save_table(df, outdir / "credito_rural")
    print(f"  credito_rural: {len(df):,} linhas -> {[Path(o).name for o in outs]}")

    write_manifest(
        "credito_rural",
        source="BCB/SICOR (MDCR)",
        reference_date=f"{args.ano_credito}-01-01",
        source_files=[str(p) for p in (RAW_DIR / "bcb").glob(f"sicor_*_{args.ano_credito}.json")],
        output_files=outs,
        row_count=len(df),
        municipality_count=df["cod_ibge"].nunique(),
        extra={"ano_credito": args.ano_credito},
    )
    print("Concluído.")


if __name__ == "__main__":
    main()
