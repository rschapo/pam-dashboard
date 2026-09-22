"""
download_pevs.py — Coletor PEVS para as bases complementares.

A PEVS já é coletada pelo gerador existente `generator/download_pevs_ibge.py`
(Silvicultura 291, Extração 289, Área 5930), que grava o consolidado
PEVS_municipios_completo.csv. Para não duplicar lógica, este script:

  * localiza o CSV consolidado (env PEVS_CSV_PATH ou o caminho canônico do projeto,
    data/raw/ibge/pevs/PEVS_municipios_completo.csv) e o copia para lá, registrando
    o manifesto. Se a origem já for o próprio destino, apenas registra o manifesto;
  * se não existir, orienta rodar o coletor original na máquina do usuário.

Assim, o pipeline complementar (process_pevs.py) consome sempre de data/raw,
mantendo rastreabilidade e reprodutibilidade sem reescrever o coletor validado.

Uso:
  python download_pevs.py
  PEVS_CSV_PATH=D:\dados\PEVS_municipios_completo.csv python download_pevs.py
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import RAW_DIR, write_manifest, today_iso  # noqa: E402

# O consolidado já vive em data/raw/ibge/pevs (migrado da antiga pasta externa).
# Mantido como cópia explícita apenas para quando PEVS_CSV_PATH apontar para fora.
PADRAO = str(RAW_DIR / "ibge" / "pevs" / "PEVS_municipios_completo.csv")


def main():
    src = Path(os.environ.get("PEVS_CSV_PATH", PADRAO))
    dst_dir = RAW_DIR / "ibge" / "pevs"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / "PEVS_municipios_completo.csv"

    if not src.exists():
        print("[PEVS] Consolidado não encontrado:", src)
        print("  Rode primeiro (na sua máquina): python generator/download_pevs_ibge.py")
        print("  Ou aponte PEVS_CSV_PATH para o CSV consolidado.")
        raise SystemExit(2)

    if src.resolve() == dst.resolve():
        print(f"[PEVS] Origem já é o destino canônico ({dst}); nada a copiar.")
    else:
        shutil.copy2(src, dst)
    write_manifest("raw_pevs", source="IBGE — PEVS (via download_pevs_ibge.py)",
                   reference_date=today_iso(), source_files=[str(src)], output_files=[str(dst)])
    print(f"[PEVS] OK — copiado para {dst}")


if __name__ == "__main__":
    main()
