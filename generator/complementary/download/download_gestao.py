"""
download_gestao.py — TSE dados abertos: baixa consulta_cand_<ano>.zip (candidatos)
para data/raw/tse/. Migrado de Base_Municipios_Brasil/scripts/coletar_base.py::
coletar_gestao (mesma fonte), agora dentro do pam-dashboard.

Só baixa o zip bruto (grande) — o filtro para prefeitos eleitos e a
normalização ficam em process_gestao.py, para poder reprocessar sem
rebaixar caso a lógica de filtro mude.

Roda na máquina do usuário (rede aberta). Uso:
  python download_gestao.py [--ano-eleicao 2024]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import RAW_DIR, today_iso, write_manifest, require_local_network  # noqa: E402

UA = {"User-Agent": "AgrocoreEstudos/1.0 (bases complementares)"}


def baixar(ano_eleicao: int) -> Path:
    import requests
    dst = RAW_DIR / "tse"
    dst.mkdir(parents=True, exist_ok=True)
    out = dst / f"consulta_cand_{ano_eleicao}.zip"
    if out.exists():
        print(f"[TSE] já baixado: {out.name} ({out.stat().st_size / 1_048_576:.1f} MB)")
        return out
    url = f"https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_{ano_eleicao}.zip"
    print(f"[TSE] baixando {url} (zip grande) …")
    r = requests.get(url, headers=UA, timeout=300, stream=True)
    r.raise_for_status()
    with open(out, "wb") as fh:
        for chunk in r.iter_content(chunk_size=1 << 20):
            fh.write(chunk)
    print(f"[TSE] gravado: {out.name} ({out.stat().st_size / 1_048_576:.1f} MB)")
    return out


def main():
    ap = argparse.ArgumentParser(description="Baixa consulta_cand do TSE (bruto)")
    ap.add_argument("--ano-eleicao", type=int, default=2024,
                     help="Ano das eleições municipais (padrão 2024, mandato 2025-2028)")
    args = ap.parse_args()

    require_local_network("TSE dados abertos")
    out = baixar(args.ano_eleicao)

    write_manifest(
        "raw_gestao",
        source="TSE — dados abertos (consulta_cand)",
        reference_date=today_iso(),
        source_files=[],
        output_files=[str(out)],
        extra={"ano_eleicao": args.ano_eleicao},
    )
    print("[OK]")


if __name__ == "__main__":
    main()
