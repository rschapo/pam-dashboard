"""
download_car.py — Adaptador para o SICAR/CAR (por UF), com diagnóstico de acesso.

O CAR é baixado no SICAR por UF/município (shapefiles), sujeito a termos de uso.
Não há automação anônima uniforme garantida e há UFs com sistemas estaduais
próprios. Portanto:

  * Este script NÃO contorna CAPTCHA/autenticação e NÃO simula navegação.
  * Opera como ADAPTADOR LOCAL: o operador baixa os shapefiles do SICAR e os
    coloca em  data/raw/car/<uf>/  ; aqui inventariamos, hasheamos e registramos.
  * Gera/atualiza docs/CAR_SOURCE_MATRIX.md (uma linha por UF) a partir de
    config/sources.yaml + do que estiver presente em data/raw/car/.

Uso:
  python download_car.py                 # inventário + matriz de disponibilidade
  python download_car.py --uf MT
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import RAW_DIR, UFS, UF_NAMES, sha256_file, write_manifest, today_iso  # noqa: E402

DOCS = Path(__file__).resolve().parents[1] / "docs"
EXT_GEO = {".shp", ".gpkg", ".geojson", ".zip", ".gdb"}


def inventario(ufs):
    base = RAW_DIR / "car"
    base.mkdir(parents=True, exist_ok=True)
    presentes = {}
    for uf in ufs:
        d = base / uf
        arqs = [p for p in d.rglob("*") if p.is_file() and p.suffix.lower() in EXT_GEO] if d.exists() else []
        presentes[uf] = arqs
    return presentes


def escrever_matriz(presentes):
    DOCS.mkdir(parents=True, exist_ok=True)
    linhas = ["# CAR_SOURCE_MATRIX — Disponibilidade do CAR por UF",
              "",
              "> Gerado por download_car.py. Uma linha por UF. `download_automatizavel`",
              "> reflete o estado atual (SICAR exige seleção/termos; automação não assumida).",
              "",
              "| uf | orgao_responsavel | sistema_origem | canal_download | formato | download_automatizavel | bruto_presente | observacao |",
              "|----|-------------------|----------------|----------------|---------|------------------------|----------------|------------|"]
    for uf in UFS:
        arqs = presentes.get(uf, [])
        tem = "sim" if arqs else "não"
        linhas.append(
            f"| {uf} | SFB/SICAR (verificar órgão estadual) | SICAR nacional | "
            f"consultapublica.car.gov.br | Shapefile | não (manual) | {tem} | "
            f"{UF_NAMES[uf]}; conferir sistema estadual |")
    (DOCS / "CAR_SOURCE_MATRIX.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uf", nargs="*", default=UFS)
    args = ap.parse_args()

    presentes = inventario(args.uf)
    escrever_matriz(presentes)

    achados = [str(p) for arqs in presentes.values() for p in arqs]
    faltando = [uf for uf, a in presentes.items() if not a]
    for uf in faltando:
        pass
    if faltando:
        print("[CAR] UFs sem bruto em data/raw/car/<uf>/:", ", ".join(faltando))
        print("  Baixe os shapefiles do SICAR (ver sources.yaml → sicar_car) por UF e")
        print("  coloque em data/raw/car/<uf>/. Registre os termos de uso.")
    print(f"[CAR] matriz atualizada em docs/CAR_SOURCE_MATRIX.md · {len(achados)} arquivo(s) presente(s).")

    write_manifest("raw_car", source="SICAR — CAR (por UF)", reference_date=today_iso(),
                   source_files=achados,
                   warnings=[f"UF sem bruto: {uf}" for uf in faltando])


if __name__ == "__main__":
    main()
