"""
process_financas.py — Constrói mun_financas a partir dos lotes brutos gravados
por download_financas.py (data/raw/siconfi/dca_lote_*.json).

BUG CORRIGIDO NESTA VERSÃO (herdado de coletar_base.py, nunca funcionou lá):
cada linha de conta do DCA-Anexo I-C vem repetida várias vezes sob "colunas"
diferentes do relatório (ex.: "Receitas Brutas Realizadas", "Deduções -
FUNDEB", "Outras Deduções da Receita") — o extrator antigo pegava qualquer
uma que aparecesse por último (dict overwrite em loop), produzindo valores
minúsculos e incorretos (uma dedução ao invés do valor bruto). Agora
filtramos por coluna == "Receitas Brutas Realizadas" e casamos por
`cod_conta` exato (não por texto de `conta`, que se repete em vários níveis
hierárquicos e contém substrings ambíguas como "impostos").

Saída: data/processed/municipality/financas.parquet | .csv
Uso: python process_financas.py [--ano-fin 2023]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import RAW_DIR, PROCESSED_DIR, cod_mun7, save_table, write_manifest  # noqa: E402

COLUNA_BRUTA = "Receitas Brutas Realizadas"
COD_CONTA_POR_CAMPO = {
    "receita_total": "ReceitasExcetoIntraOrcamentarias",       # RECEITAS (EXCETO INTRA-ORÇAMENTÁRIAS) (I)
    "receita_corrente": "RO1.0.0.0.00.0.0",                    # 1.0.0.0.00.0.0 - Receitas Correntes
    "receita_tributaria_propria": "RO1.1.0.0.00.0.0",          # 1.1.0.0.00.0.0 - Impostos, Taxas e Contrib. de Melhoria
    "transferencias_correntes": "RO1.7.0.0.00.0.0",            # 1.7.0.0.00.0.0 - Transferências Correntes
}


def build(ano_fin: int) -> pd.DataFrame:
    lotes = sorted((RAW_DIR / "siconfi").glob("dca_lote_*.json"))
    if not lotes:
        raise SystemExit("Nenhum lote em data/raw/siconfi/ — rode download_financas.py antes.")

    campo_por_cod_conta = {v: k for k, v in COD_CONTA_POR_CAMPO.items()}
    registros = []
    for p in lotes:
        for ente in json.loads(p.read_text(encoding="utf-8")):
            cod = cod_mun7(ente.get("cod_ibge"))
            if not cod:
                continue
            reg = {"cod_ibge": cod, "ano_ref": ano_fin, "fonte": "STN/SICONFI"}
            for it in ente.get("items", []):
                if it.get("coluna") != COLUNA_BRUTA:
                    continue
                campo = campo_por_cod_conta.get(it.get("cod_conta"))
                if campo:
                    reg[campo] = it.get("valor")
            registros.append(reg)

    df = pd.DataFrame(registros)
    for c in COD_CONTA_POR_CAMPO:
        if c not in df:
            df[c] = None
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["resultado_orcamentario"] = df["receita_total"] - df.get("despesa_total", pd.Series(dtype=float))
    df = df.drop_duplicates("cod_ibge").sort_values("cod_ibge").reset_index(drop=True)
    return df


def main():
    ap = argparse.ArgumentParser(description="Constrói mun_financas (SICONFI)")
    ap.add_argument("--ano-fin", type=int, default=2023)
    args = ap.parse_args()

    df = build(args.ano_fin)
    outdir = PROCESSED_DIR / "municipality"
    outs = save_table(df, outdir / "financas")
    print(f"  financas: {len(df):,} municípios -> {[Path(o).name for o in outs]}")

    write_manifest(
        "financas",
        source="STN/SICONFI (DCA-Anexo I-C)",
        reference_date=f"{args.ano_fin}-01-01",
        source_files=[str(p) for p in (RAW_DIR / "siconfi").glob("dca_lote_*.json")],
        output_files=outs,
        row_count=len(df),
        municipality_count=df["cod_ibge"].nunique(),
        extra={"ano_fin": args.ano_fin},
    )
    print("Concluído.")


if __name__ == "__main__":
    main()
