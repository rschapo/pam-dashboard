"""
run_pipeline.py — Orquestrador das bases complementares (Etapas 1 e 2).

Executa os passos na ordem do briefing (seção 13). Cada passo é idempotente e
tolera fonte ausente (registra e segue). Os DOWNLOADS oficiais só funcionam na
máquina do usuário (rede aberta); em ambiente com allowlist, use --no-download
para rodar apenas o PROCESSAMENTO sobre o que já estiver em data/raw.

Exemplos:
  python run_pipeline.py --stage 1                 # Etapa 1 completa
  python run_pipeline.py --stage 1 --no-download   # só processa o que há em data/raw
  python run_pipeline.py --stage 2 --uf MT         # Etapa 2 (CAR/MapBiomas), UF piloto MT
  python run_pipeline.py --only geography          # um passo só
"""
from __future__ import annotations

import argparse
import runpy
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import update_global_manifest  # noqa: E402

DOWNLOAD = HERE / "download"
PROCESS = HERE / "process"
QUALITY = HERE / "quality"


def _run(script: Path, argv=None):
    print(f"\n{'='*70}\n>> {script.parent.name}/{script.name} {' '.join(argv or [])}\n{'='*70}")
    old = sys.argv
    sys.argv = [str(script)] + (argv or [])
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as e:
        if e.code not in (0, None):
            print(f"  (passo sinalizou saída {e.code} — seguindo)")
    except Exception as e:  # noqa: BLE001
        print(f"  [ERRO no passo] {type(e).__name__}: {e}")
    finally:
        sys.argv = old


def stage1(download: bool):
    if download:
        _run(DOWNLOAD / "download_ibge_geography.py")
        _run(DOWNLOAD / "download_ibge_areas.py")
        _run(DOWNLOAD / "download_modulo_fiscal.py")
        _run(DOWNLOAD / "download_censo_agro.py")
        _run(DOWNLOAD / "download_sncr.py")
        _run(DOWNLOAD / "download_pevs.py")
    _run(PROCESS / "process_geography.py")
    _run(QUALITY / "validate_geography.py")
    _run(PROCESS / "process_modulo_fiscal.py")
    _run(PROCESS / "process_censo_agro.py")
    _run(PROCESS / "process_sncr.py")
    _run(PROCESS / "process_pevs.py")
    _run(QUALITY / "validate_fundiary_data.py")
    _run(PROCESS / "build_rural_profile.py", ["--stage", "1"])


def stage2(download: bool, uf: str | None):
    if download:
        _run(DOWNLOAD / "download_car.py", (["--uf", uf] if uf else []))
        _run(DOWNLOAD / "download_mapbiomas.py")
    if uf:
        _run(PROCESS / "process_car.py", ["--uf", uf])
        _run(QUALITY / "validate_car_geometry.py")
    _run(PROCESS / "process_mapbiomas.py")
    _run(PROCESS / "build_rural_profile.py", ["--stage", "2"])


def stage3():
    """Etapa 3/4 (offline): exporta JSONs de front-end + protótipo de aba.
    Separado de public/data — não altera a produção."""
    _run(PROCESS / "export_frontend.py")
    _run(PROCESS / "build_preview.py")


def main():
    ap = argparse.ArgumentParser(description="Pipeline das bases complementares (Agrocore)")
    ap.add_argument("--stage", choices=["1", "2", "3"], default="1")
    ap.add_argument("--uf", help="UF piloto para a Etapa 2 (CAR)")
    ap.add_argument("--no-download", action="store_true", help="pula os coletores (só processa data/raw)")
    ap.add_argument("--only", help="roda um único passo (nome do script sem .py)")
    args = ap.parse_args()

    if args.only:
        for base in (PROCESS, DOWNLOAD, QUALITY):
            cand = base / f"{args.only}.py"
            if cand.exists():
                _run(cand)
                update_global_manifest()
                return
        raise SystemExit(f"passo '{args.only}' não encontrado")

    download = not args.no_download
    if args.stage == "1":
        stage1(download)
    elif args.stage == "2":
        stage2(download, args.uf)
    else:
        stage3()

    _run(QUALITY / "validate_outputs.py")
    mani = update_global_manifest()
    print(f"\n✔ Pipeline concluído. Manifesto geral: {mani}")


if __name__ == "__main__":
    main()
