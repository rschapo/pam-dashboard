"""
download_sncr.py — Adaptador para os dados públicos do SNCR (INCRA), por UF.

O SNCR (Sistema Nacional de Cadastro Rural) disponibiliza dados públicos de
imóveis rurais. O download é feito POR UF no portal do INCRA (ver sources.yaml);
não há endpoint anônimo estável e uniforme para automação nacional — por isso o
padrão aqui é ADAPTADOR LOCAL, preservando o bruto por UF:

  data/raw/sncr/<uf>/<arquivo original>

Este script inventaria o que já foi colocado em data/raw/sncr/, registra hashes e
gera o manifesto. Não coleta titular (CPF/CNPJ/nome) e não reidentifica pessoas
(seção 2.3). Se o INCRA publicar um pacote automatizável no futuro, acrescente a
função de coleta respeitando os termos de uso.

Uso:
  python download_sncr.py            # inventaria o que existe em data/raw/sncr/
  python download_sncr.py --uf MT PA
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import RAW_DIR, UFS, sha256_file, write_manifest, today_iso  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uf", nargs="*", default=UFS)
    args = ap.parse_args()

    base = RAW_DIR / "sncr"
    base.mkdir(parents=True, exist_ok=True)
    achados, faltando = [], []
    for uf in args.uf:
        d = base / uf
        arqs = [p for p in d.glob("*") if p.is_file()] if d.exists() else []
        if arqs:
            for p in arqs:
                achados.append({"uf": uf, "arquivo": p.name, "bytes": p.stat().st_size,
                                "sha256": sha256_file(p)})
        else:
            faltando.append(uf)

    if faltando:
        print("[SNCR] UFs sem bruto em data/raw/sncr/<uf>/:", ", ".join(faltando))
        print("  Baixe os dados públicos do SNCR por UF (ver config/sources.yaml → incra_sncr)")
        print("  e coloque cada arquivo em data/raw/sncr/<uf>/. Preserve o original.")
    if achados:
        print(f"[SNCR] {len(achados)} arquivo(s) presentes em {len(args.uf)-len(faltando)} UF(s).")

    write_manifest("raw_sncr", source="INCRA — SNCR (imóveis rurais, por UF)",
                   reference_date=today_iso(),
                   source_files=[str(base / a['uf'] / a['arquivo']) for a in achados],
                   warnings=[f"UF sem bruto: {uf}" for uf in faltando],
                   extra={"arquivos": achados})


if __name__ == "__main__":
    main()
