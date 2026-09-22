"""
download_mapbiomas.py — Adaptador para as estatísticas municipais do MapBiomas.

MapBiomas é fonte COMPLEMENTAR (não substitui fonte oficial). A estatística
municipal de área por classe é publicada como XLSX no portal de Estatísticas; o
raster de cobertura fica no Google Earth Engine (coleção). O download da planilha
não tem endpoint anônimo estável garantido — padrão ADAPTADOR LOCAL:

  data/raw/mapbiomas/mapbiomas_cobertura_municipios.xlsx   (planilha oficial)

Registre a COLEÇÃO e a VERSÃO (ex.: Coleção 9) — vão para o manifesto e para a
tabela final (campos colecao/versao). A licença CC-BY-SA exige citar a fonte.

Uso:
  python download_mapbiomas.py --colecao 9 --versao "Coleção 9"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import RAW_DIR, write_manifest, today_iso  # noqa: E402

CANDIDATOS = [
    "mapbiomas_cobertura_municipios.xlsx",
    "mapbiomas_cobertura_municipios.csv",
    "ESTATISTICAS_MapBiomas.xlsx",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--colecao", default=None, help="número da coleção (ex.: 9)")
    ap.add_argument("--versao", default=None, help="rótulo da versão (ex.: 'Coleção 9')")
    args = ap.parse_args()

    dst = RAW_DIR / "mapbiomas"
    dst.mkdir(parents=True, exist_ok=True)
    achado = next((dst / c for c in CANDIDATOS if (dst / c).exists()), None)
    if not achado:
        print("[MAPBIOMAS] Planilha de estatísticas não encontrada.")
        print("  Baixe as Estatísticas (área por classe × município) do portal MapBiomas")
        print("  (ver sources.yaml → mapbiomas) e salve como:")
        print(f"    {dst / 'mapbiomas_cobertura_municipios.xlsx'}")
        print("  Informe --colecao e --versao para rastreabilidade.")
        raise SystemExit(2)

    write_manifest("raw_mapbiomas", source="MapBiomas — Estatísticas municipais",
                   reference_date=today_iso(), source_files=[str(achado)],
                   output_files=[str(achado)],
                   extra={"colecao": args.colecao, "versao": args.versao,
                          "licenca": "CC-BY-SA"})
    print(f"[MAPBIOMAS] OK — bruto presente: {achado.name} | coleção={args.colecao} versão={args.versao}")


if __name__ == "__main__":
    main()
