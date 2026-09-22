"""
process_gestao.py — Extrai prefeitos eleitos do zip bruto do TSE
(data/raw/tse/consulta_cand_<ano>.zip, baixado por download_gestao.py).

LIMITAÇÃO CONHECIDA (herdada de Base_Municipios_Brasil/README.md §1, nunca
resolvida lá): o TSE usa código próprio de município (SG_UE), diferente do
cod_ibge (7 dígitos) usado no resto desta base. Sem um de-para TSE↔IBGE
(data/raw/tse/depara_tse_ibge.csv, colunas cod_tse_municipio;cod_ibge — não
existe hoje), a saída fica com a chave TSE, não cruzável automaticamente com
PAM/PPM/PEVS/demografia/finanças. Se esse de-para for obtido, o script já usa
automaticamente. Até lá, mun_gestao é utilizável isoladamente (nome do
gestor por município/UF) mas não deve ser junctionado por cod_ibge.

Saída: data/processed/municipality/gestao.parquet | .csv
Uso: python process_gestao.py [--ano-eleicao 2024]
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import RAW_DIR, PROCESSED_DIR, save_table, write_manifest  # noqa: E402


def build(ano_eleicao: int) -> pd.DataFrame:
    zpath = RAW_DIR / "tse" / f"consulta_cand_{ano_eleicao}.zip"
    if not zpath.exists():
        raise SystemExit(f"Não encontrado: {zpath}\nRode antes: python download_gestao.py")

    with zipfile.ZipFile(zpath) as z:
        csvs = [n for n in z.namelist() if n.lower().endswith(".csv") and "BRASIL" not in n.upper()]
        frames = []
        for nome in csvs:
            with z.open(nome) as fh:
                df = pd.read_csv(io.TextIOWrapper(fh, encoding="latin-1"), sep=";",
                                 dtype=str, quoting=csv.QUOTE_ALL, on_bad_lines="skip")
            df = df[df["DS_CARGO"].str.upper() == "PREFEITO"]
            df = df[df["DS_SIT_TOT_TURNO"].str.upper().str.startswith("ELEITO", na=False)]
            frames.append(df)
    tse = pd.concat(frames, ignore_index=True)

    out = pd.DataFrame({
        "cod_tse_municipio": tse.get("SG_UE"),
        "nome_municipio_tse": tse.get("NM_UE"),
        "sigla_uf": tse.get("SG_UF"),
        "mandato": f"{ano_eleicao + 1}-{ano_eleicao + 4}",
        "nome_gestor": tse.get("NM_CANDIDATO"),
        "nome_urna": tse.get("NM_URNA_CANDIDATO"),
        "partido": tse.get("SG_PARTIDO"),
        "situacao": tse.get("DS_SIT_TOT_TURNO"),
        "fonte": "TSE (dados abertos)",
    })

    depara_path = RAW_DIR / "tse" / "depara_tse_ibge.csv"
    tem_depara = depara_path.exists()
    if tem_depara:
        dp = pd.read_csv(depara_path, sep=";", dtype=str)
        out = out.merge(dp, on="cod_tse_municipio", how="left")
    else:
        print("  [AVISO] de-para TSE->IBGE ausente (data/raw/tse/depara_tse_ibge.csv) — "
              "saída fica com chave TSE, não cruzável por cod_ibge. Ver docstring deste script.")
    return out, tem_depara


def main():
    ap = argparse.ArgumentParser(description="Constrói mun_gestao (TSE — prefeitos eleitos)")
    ap.add_argument("--ano-eleicao", type=int, default=2024)
    args = ap.parse_args()

    df, tem_depara = build(args.ano_eleicao)
    outdir = PROCESSED_DIR / "municipality"
    outs = save_table(df, outdir / "gestao")
    print(f"  gestao: {len(df):,} prefeitos eleitos -> {[Path(o).name for o in outs]}")

    write_manifest(
        "gestao",
        source="TSE — dados abertos (consulta_cand)",
        reference_date=f"{args.ano_eleicao}-10-01",
        source_files=[str(RAW_DIR / 'tse' / f'consulta_cand_{args.ano_eleicao}.zip')],
        output_files=outs,
        row_count=len(df),
        warnings=[] if tem_depara else ["chave cod_ibge ausente — de-para TSE->IBGE não encontrado"],
        extra={"ano_eleicao": args.ano_eleicao, "chave_cod_ibge_disponivel": tem_depara},
    )
    print("Concluído.")


if __name__ == "__main__":
    main()
