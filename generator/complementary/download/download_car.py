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

# Subpastas esperadas em data/raw/car/<uf>/. O perímetro do imóvel sustenta o
# resumo fundiário; as camadas ambientais são baixadas à parte no SICAR e hoje
# faltam na maioria das UFs, por isso a matriz distingue uma coisa da outra.
CAMADA_IMOVEIS = "imoveis"
CAMADAS_AMBIENTAIS = ["area_consolidada", "vegetacao_nativa", "reserva_legal",
                      "app", "uso_restrito"]


def inventario(ufs):
    """Devolve {uf: {camada: [arquivos]}} — arquivo solto na raiz conta como imóveis."""
    base = RAW_DIR / "car"
    base.mkdir(parents=True, exist_ok=True)
    presentes = {}
    for uf in ufs:
        d = base / uf
        por_camada = {}
        if d.exists():
            for sub in sorted(d.iterdir()):
                if not sub.is_dir():
                    continue
                arqs = [q for q in sub.rglob("*")
                        if q.is_file() and q.suffix.lower() in EXT_GEO]
                if arqs:
                    por_camada[sub.name] = arqs
            soltos = [q for q in d.glob("*")
                      if q.is_file() and q.suffix.lower() in EXT_GEO]
            if soltos:
                por_camada.setdefault(CAMADA_IMOVEIS, []).extend(soltos)
        presentes[uf] = por_camada
    return presentes


def todos_arquivos(presentes):
    return [str(q) for camadas in presentes.values()
            for arqs in camadas.values() for q in arqs]


def escrever_matriz(presentes):
    DOCS.mkdir(parents=True, exist_ok=True)
    linhas = ["# CAR_SOURCE_MATRIX — Disponibilidade do CAR por UF",
              "",
              "> Gerado por download_car.py. O SICAR exige seleção e aceite de termos, então",
              "> nenhum download aqui é automatizável: o operador baixa e deposita em",
              "> `data/raw/car/<uf>/<camada>/`. Esta tabela é a checklist do que já chegou.",
              "",
              "> `imoveis` sustenta o resumo fundiário publicado (imóveis, área declarada,",
              "> área média, sobreposição). As camadas ambientais — área consolidada,",
              "> vegetação nativa, reserva legal, APP e uso restrito — são baixadas à parte",
              "> e alimentam `process_car_layers.py`.",
              "",
              "| uf | nome | imóveis | camadas ambientais | falta baixar |",
              "|----|------|---------|--------------------|--------------|"]
    for uf in UFS:
        camadas = presentes.get(uf, {})
        tem_imoveis = "sim" if camadas.get(CAMADA_IMOVEIS) else "**não**"
        presentes_amb = [c for c in CAMADAS_AMBIENTAIS if camadas.get(c)]
        faltam_amb = [c for c in CAMADAS_AMBIENTAIS if not camadas.get(c)]
        amb = (f"{len(presentes_amb)}/{len(CAMADAS_AMBIENTAIS)} — " +
               ", ".join(presentes_amb)) if presentes_amb else "0/5"
        falta = ", ".join(([] if camadas.get(CAMADA_IMOVEIS) else [CAMADA_IMOVEIS]) + faltam_amb) or "—"
        linhas.append(f"| {uf} | {UF_NAMES[uf]} | {tem_imoveis} | {amb} | {falta} |")
    (DOCS / "CAR_SOURCE_MATRIX.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uf", nargs="*", default=UFS)
    args = ap.parse_args()

    presentes = inventario(args.uf)
    escrever_matriz(presentes)

    achados = todos_arquivos(presentes)
    sem_imoveis = [uf for uf, c in presentes.items() if not c.get(CAMADA_IMOVEIS)]
    sem_ambiental = [uf for uf, c in presentes.items()
                     if not any(c.get(k) for k in CAMADAS_AMBIENTAIS)]
    if sem_imoveis:
        print("[CAR] sem perímetro de imóveis:", ", ".join(sem_imoveis))
        print("  Baixe do SICAR (ver sources.yaml → sicar_car) e coloque em")
        print("  data/raw/car/<uf>/imoveis/. Registre os termos de uso.")
    if sem_ambiental:
        print(f"[CAR] sem camada ambiental ({len(sem_ambiental)} UFs):", ", ".join(sem_ambiental))
        print("  Sem elas, process_car_layers.py não tem o que agregar e o painel")
        print("  fica só com o resumo fundiário.")
    print(f"[CAR] matriz atualizada em docs/CAR_SOURCE_MATRIX.md · {len(achados)} arquivo(s).")

    write_manifest("raw_car", source="SICAR — CAR (por UF)", reference_date=today_iso(),
                   source_files=achados,
                   warnings=([f"UF sem imóveis: {uf}" for uf in sem_imoveis] +
                             [f"UF sem camada ambiental: {uf}" for uf in sem_ambiental]))


if __name__ == "__main__":
    main()
