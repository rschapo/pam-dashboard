"""
download_credito_rural.py — Banco Central, Matriz de Dados do Crédito Rural
(MDCR/SICOR), granularidade municipal. Migrado de Base_Municipios_Brasil/
scripts/coletar_base.py::coletar_credito_rural (mesma fonte/lógica).

Contratações por município via API Olinda (SICOR v2), finalidade
custeio/investimento. O $apply/groupby do SICOR é ignorado pelo servidor
(devolve dado cru), então agregamos localmente com pandas — por isso uma
chamada pode levar até ~20 min (milhões de linhas cruas por finalidade/ano).

BUG CORRIGIDO NESTA VERSÃO (herdado de coletar_base.py, nunca funcionou lá):
o recurso "CusteioMunicipioProduto" tem o campo `codIbge` direto, mas
"InvestMunicipioProduto" NÃO TEM — só `cdMunicipio` (código interno do BCB,
não é o cod_ibge de 7 dígitos) + `Municipio` (nome) + `cdEstado` (código de
UF interno do BCB, também não é o da IBGE). Por isso a coleta de Investimento
sempre vinha 100% vazia/nula antes. Agora: detecta os campos disponíveis por
recurso e, quando não há codIbge, baixa nome+cdEstado também — a resolução
para cod_ibge (via nome+UF, com cdEstado→UF traduzido pelo recurso RegiaoUF)
fica em process_credito_rural.py.

Roda na máquina do usuário (rede aberta). Uso:
  python download_credito_rural.py [--ano-credito 2024]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import RAW_DIR, today_iso, write_manifest, require_local_network  # noqa: E402

UA = {"User-Agent": "AgrocoreEstudos/1.0 (bases complementares)"}
BASE_URL = "https://olinda.bcb.gov.br/olinda/servico/SICOR/versao/v2/odata"
RECURSOS = {"Custeio": "CusteioMunicipioProduto", "Investimento": "InvestMunicipioProduto"}


def _campos_disponiveis(recurso: str) -> dict:
    import requests
    r = requests.get(f"{BASE_URL}/{recurso}?$top=1&$format=json", headers=UA, timeout=120)
    r.raise_for_status()
    rec = (r.json().get("value") or [{}])[0]
    return {
        "vl": next((k for k in rec if k.lower().startswith("vl")), None),
        "area": next((k for k in rec if k.lower().startswith("area") or k.lower().startswith("ar")), None),
        "cod_ibge": next((k for k in rec if k.lower() == "codibge"), None),
        "municipio": next((k for k in rec if k.lower() == "municipio"), None),
        "cd_estado": next((k for k in rec if k.lower() == "cdestado"), None),
    }


def _baixar_regiaouf_lookup(dst: Path) -> Path:
    """RegiaoUF traz (cdEstado, nomeUF) — único jeito de traduzir o cdEstado
    interno do BCB usado em InvestMunicipioProduto. Página pequena, poucos
    segundos: pega o suficiente para cobrir os 27 estados."""
    import requests
    out = dst / "sicor_regiaouf_lookup.json"
    if out.exists():
        return out
    url = f"{BASE_URL}/RegiaoUF?$select=cdEstado,nomeUF&$top=2000&$format=json"
    r = requests.get(url, headers=UA, timeout=120)
    r.raise_for_status()
    out.write_text(json.dumps(r.json(), ensure_ascii=False), encoding="utf-8")
    return out


def baixar(ano_credito: int) -> list[Path]:
    import requests
    dst = RAW_DIR / "bcb"
    dst.mkdir(parents=True, exist_ok=True)
    saidas = [_baixar_regiaouf_lookup(dst)]

    for finalidade, recurso in RECURSOS.items():
        out = dst / f"sicor_{finalidade.lower()}_{ano_credito}.json"
        if out.exists():
            print(f"[BCB] {finalidade}: já baixado ({out.stat().st_size / 1_048_576:.1f} MB)")
            saidas.append(out)
            continue
        campos = _campos_disponiveis(recurso)
        if not campos["vl"]:
            print(f"    ! {finalidade}: campo de valor não identificado; pulando.")
            continue
        if campos["cod_ibge"]:
            sel_campos = [campos["cod_ibge"], campos["vl"], campos["area"]]
        else:
            print(f"    ! {finalidade}: sem codIbge no recurso — usando "
                  f"{campos['municipio']}+{campos['cd_estado']} (resolvido depois por nome+UF)")
            sel_campos = [campos["municipio"], campos["cd_estado"], campos["vl"], campos["area"]]
        sel = ",".join(c for c in sel_campos if c)
        url = f"{BASE_URL}/{recurso}?$filter=AnoEmissao eq '{ano_credito}'&$select={sel}&$format=json"
        print(f"[BCB] {finalidade}: baixando (pode levar até ~20 min) …")
        r = requests.get(url, headers=UA, timeout=1200)
        r.raise_for_status()
        out.write_text(json.dumps(r.json(), ensure_ascii=False), encoding="utf-8")
        print(f"    -> {out.name} ({out.stat().st_size / 1_048_576:.1f} MB)")
        saidas.append(out)

    return saidas


def main():
    ap = argparse.ArgumentParser(description="Baixa SICOR/MDCR brutos (crédito rural municipal)")
    ap.add_argument("--ano-credito", type=int, default=2024)
    args = ap.parse_args()

    require_local_network("BCB/SICOR")
    saidas = baixar(args.ano_credito)
    if not saidas:
        print("[AVISO] Coleta indisponível. Alternativa: baixar a MDCR em")
        print("  https://dadosabertos.bcb.gov.br/dataset/matrizdadoscreditorural")
        return

    write_manifest(
        "raw_credito_rural",
        source="BCB/SICOR (MDCR)",
        reference_date=today_iso(),
        source_files=[],
        output_files=[str(p) for p in saidas],
        extra={"ano_credito": args.ano_credito},
    )
    print(f"[OK] {len(saidas)} arquivo(s) gravados em data/raw/bcb/")


if __name__ == "__main__":
    main()
