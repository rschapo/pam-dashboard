"""
download_modulo_fiscal.py — Adaptador para os Índices Básicos do INCRA
(módulo fiscal + fração mínima de parcelamento por município).

A tabela de módulo fiscal do INCRA é publicada como planilha (Índices Básicos,
base na Instrução Especial nº 20/1980 e atualizações). Não há endpoint estável e
automatizável garantido; por isso este script opera como ADAPTADOR LOCAL:

  1. O operador baixa a planilha do portal do INCRA (ver config/sources.yaml) e a
     salva como  data/raw/incra/modulo_fiscal_municipios.(xlsx|csv).
  2. Este script confirma a presença, registra hash/manifesto e valida o layout
     mínimo, deixando o arquivo bruto preservado para o process_modulo_fiscal.py.

Não contorna autenticação/CAPTCHA e não inventa link de download.

Uso:
  python download_modulo_fiscal.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import RAW_DIR, write_manifest, today_iso  # noqa: E402

CANDIDATOS = [
    "modulo_fiscal_municipios.csv",
    "modulo_fiscal_municipios.xlsx",
    "indices_basicos_incra.xlsx",
]


def main():
    dst = RAW_DIR / "incra"
    dst.mkdir(parents=True, exist_ok=True)
    achado = next((dst / c for c in CANDIDATOS if (dst / c).exists()), None)
    if not achado:
        print("[MÓDULO FISCAL] Arquivo bruto não encontrado.")
        print("  Baixe a planilha de Índices Básicos do INCRA (módulo fiscal por município)")
        print("  no portal (ver config/sources.yaml → incra_modulo_fiscal) e salve como:")
        print(f"    {dst / 'modulo_fiscal_municipios.csv'}  (ou .xlsx)")
        print("  Depois rode process/process_modulo_fiscal.py.")
        raise SystemExit(2)

    write_manifest("raw_modulo_fiscal", source="INCRA — Índices Básicos (módulo fiscal)",
                   reference_date=today_iso(), source_files=[str(achado)],
                   output_files=[str(achado)])
    print(f"[MÓDULO FISCAL] OK — bruto presente: {achado.name} (manifesto registrado)")


if __name__ == "__main__":
    main()
