"""
download_financas.py — SICONFI/Tesouro (DCA, Declaração de Contas Anuais) por
município. Migrado de Base_Municipios_Brasil/scripts/coletar_base.py::
coletar_financas (mesma fonte/lógica), agora dentro do pam-dashboard.

É a coleta mais demorada do pipeline (milhares de chamadas, ~1 por município).
Salva em lotes de 200 entes em data/raw/siconfi/ para permitir retomar se
interrompido — um lote já salvo é pulado (idempotente).

Roda na máquina do usuário (rede aberta). Uso:
  python download_financas.py [--ano-fin 2023]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import RAW_DIR, today_iso, write_manifest, require_local_network  # noqa: E402

UA = {"User-Agent": "AgrocoreEstudos/1.0 (bases complementares)"}
BASE_URL = "https://apidatalake.tesouro.gov.br/ords/siconfi"
LOTE = 200


def _get(url: str, params=None, tries: int = 4, backoff: int = 3):
    import requests
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=60)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if i == tries - 1:
                raise
            wait = backoff * (2 ** i)
            print(f"    ! falha ({e}); retry em {wait}s")
            time.sleep(wait)


def listar_municipios() -> list[dict]:
    entes = _get(f"{BASE_URL}/tt/entes")["items"]
    return [e for e in entes if str(e.get("cod_ibge", "")).__len__() == 7 and e.get("esfera") == "M"]


def caminho_lote(dst: Path, i: int) -> Path:
    return dst / f"dca_lote_{i:05d}.json"


def baixar(ano_fin: int) -> Path:
    dst = RAW_DIR / "siconfi"
    dst.mkdir(parents=True, exist_ok=True)

    municipios = listar_municipios()
    print(f"[SICONFI] {len(municipios)} municípios — ano {ano_fin}")

    for inicio in range(0, len(municipios), LOTE):
        lote_idx = inicio // LOTE
        p = caminho_lote(dst, lote_idx)
        if p.exists():
            continue  # retomada: lote já baixado
        lote = municipios[inicio:inicio + LOTE]
        registros = []
        for e in lote:
            cod = e["cod_ibge"]
            try:
                items = _get(f"{BASE_URL}/tt/dca",
                             params={"an_exercicio": ano_fin, "id_ente": cod,
                                     "no_anexo": "DCA-Anexo I-C"})["items"]
                registros.append({"cod_ibge": cod, "items": items})
            except Exception as ex:
                print(f"    ! ente {cod} falhou: {ex}")
                registros.append({"cod_ibge": cod, "items": [], "erro": str(ex)})
            time.sleep(0.15)  # gentileza com a API
        p.write_text(json.dumps(registros, ensure_ascii=False), encoding="utf-8")
        print(f"    lote {lote_idx}: {inicio + len(lote)}/{len(municipios)} entes -> {p.name}")

    return dst


def main():
    ap = argparse.ArgumentParser(description="Baixa SICONFI/DCA por município (resumível)")
    ap.add_argument("--ano-fin", type=int, default=2023, help="Exercício financeiro (padrão 2023)")
    args = ap.parse_args()

    require_local_network("SICONFI/Tesouro")
    dst = baixar(args.ano_fin)

    lotes = sorted(dst.glob("dca_lote_*.json"))
    write_manifest(
        "raw_financas",
        source="STN/SICONFI (DCA-Anexo I-C)",
        reference_date=today_iso(),
        source_files=[],
        output_files=[str(p) for p in lotes],
        extra={"ano_fin": args.ano_fin, "n_lotes": len(lotes)},
    )
    print(f"[OK] {len(lotes)} lotes gravados em data/raw/siconfi/")


if __name__ == "__main__":
    main()
