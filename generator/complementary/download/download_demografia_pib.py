"""
download_demografia_pib.py — Baixa População (estimativas IBGE) e PIB/VAB dos
Municípios (SIDRA) e grava os JSONs brutos em data/raw/ibge/.

Fontes:
  População  — tabela 6579, variável 9324 (estimativa)
  PIB total  — tabela 5938, variável 37
  VAB setorial — tabela 5938, variáveis 513 (Agropecuária), 517 (Indústria),
               6575 (Serviços), 543 (Impostos líquidos)
               (PIB per capita não existe como variável na 5938 — é calculado em
               process_demografia_pib.py como pib_total / população)

IMPORTANTE — descompasso de defasagem confirmado nesta coleta: no nível
municipal, o PIB TOTAL está disponível até um ano mais recente do que o
detalhamento por VAB setorial (a IBGE publica a decomposição setorial com
mais atraso). Por isso este script busca PIB total e VAB setorial
SEPARADAMENTE: PIB total no --ano-pib pedido; VAB setorial no ano mais
recente que realmente tiver dado (testa --ano-pib, --ano-pib-1, --ano-pib-2,
...), registrando o ano efetivo no nome do arquivo e no manifesto — nunca
mistura anos diferentes sob um único rótulo "ano_ref" sem declarar.

Migrado de Base_Municipios_Brasil/scripts/coletar_base.py::coletar_demografia_pib
(mesma fonte/tabelas), agora dentro do pam-dashboard — pasta única de dados,
sem duplicar a coleta em dois projetos. Resolve o item C do
BRIEFING_DADOS_PAM_IBGE.md (atualização do VAB/PIB de 2021 para 2023).

Roda na máquina do usuário (rede aberta). Uso:
  python download_demografia_pib.py [--ano-pib 2023] [--ano-pop 2024]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import RAW_DIR, today_iso, write_manifest, require_local_network  # noqa: E402

API_SIDRA = "https://apisidra.ibge.gov.br/values"
UA = {"User-Agent": "AgrocoreEstudos/1.0 (bases complementares)"}

PIB_TOTAL_VAR = "37"
VAB_VARIAVEIS = "513,517,6575,543"
POP_VARIAVEL = "9324"
MAX_ANOS_RETROCESSO_VAB = 4


def _get(url: str, tries: int = 4, backoff: int = 3):
    import requests
    for i in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=90)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if i == tries - 1:
                raise
            wait = backoff * (2 ** i)
            print(f"    ! falha ({e}); retry em {wait}s")
            time.sleep(wait)


def _sidra_url(tabela: str, nivel: str, variaveis: str, periodo: int) -> str:
    return f"{API_SIDRA}/t/{tabela}/n{nivel}/all/v/{variaveis}/p/{periodo}"


def _tem_dado(resposta: list) -> bool:
    """True se ao menos uma linha tem valor numérico real (não '...'/'-'/'X')."""
    for row in resposta[1:]:
        v = str(row.get("V", "")).strip()
        if v not in ("", "-", "..", "...", "X", "x"):
            try:
                float(v)
                return True
            except ValueError:
                pass
    return False


def baixar(ano_pib: int, ano_pop: int) -> dict[str, Path]:
    dst = RAW_DIR / "ibge"
    dst.mkdir(parents=True, exist_ok=True)
    saidas = {}
    ano_vab_efetivo = {}

    for nivel, escopo in (("6", "municipios"), ("3", "uf")):
        print(f"[POP] tabela 6579 — {escopo}, ano {ano_pop}")
        pop = _get(_sidra_url("6579", nivel, POP_VARIAVEL, ano_pop))
        p = dst / f"sidra_populacao_{escopo}_{ano_pop}.json"
        p.write_text(json.dumps(pop, ensure_ascii=False), encoding="utf-8")
        saidas[f"pop_{escopo}"] = p

        print(f"[PIB total] tabela 5938 — {escopo}, ano {ano_pib}")
        pib_total = _get(_sidra_url("5938", nivel, PIB_TOTAL_VAR, ano_pib))
        p2 = dst / f"sidra_pibtotal_{escopo}_{ano_pib}.json"
        p2.write_text(json.dumps(pib_total, ensure_ascii=False), encoding="utf-8")
        saidas[f"pibtotal_{escopo}"] = p2

        # VAB setorial: publicado com mais atraso que o PIB total no nível
        # municipal — testa do ano pedido para trás até achar dado real.
        ano_tentativa = ano_pib
        vab = None
        for _ in range(MAX_ANOS_RETROCESSO_VAB + 1):
            print(f"[VAB setorial] tabela 5938 — {escopo}, tentando ano {ano_tentativa} …")
            resp = _get(_sidra_url("5938", nivel, VAB_VARIAVEIS, ano_tentativa))
            if _tem_dado(resp):
                vab = resp
                break
            print(f"    sem dado em {ano_tentativa}; tentando {ano_tentativa - 1}")
            ano_tentativa -= 1
        if vab is None:
            print(f"    [AVISO] nenhum ano com VAB setorial encontrado (testados até {ano_tentativa+1})")
            ano_tentativa = ano_pib  # registra o pedido original mesmo vazio
            vab = resp
        ano_vab_efetivo[escopo] = ano_tentativa
        p3 = dst / f"sidra_vabsetorial_{escopo}_{ano_tentativa}.json"
        p3.write_text(json.dumps(vab, ensure_ascii=False), encoding="utf-8")
        saidas[f"vab_{escopo}"] = p3
        print(f"    VAB setorial efetivo: {ano_tentativa}")

    saidas["_ano_vab_efetivo"] = ano_vab_efetivo
    return saidas


def main():
    ap = argparse.ArgumentParser(description="Baixa População + PIB/VAB (SIDRA) brutos")
    ap.add_argument("--ano-pib", type=int, default=2023,
                     help="Ano do PIB dos Municípios (tabela 5938). Padrão: 2023.")
    ap.add_argument("--ano-pop", type=int, default=2024,
                     help="Ano da estimativa populacional (tabela 6579). Padrão: 2024.")
    args = ap.parse_args()

    require_local_network("SIDRA Demografia/PIB")
    saidas = baixar(args.ano_pib, args.ano_pop)
    ano_vab_efetivo = saidas.pop("_ano_vab_efetivo")

    write_manifest(
        "raw_demografia_pib",
        source="IBGE/SIDRA (tabelas 5938 e 6579)",
        reference_date=today_iso(),
        source_files=[],
        output_files=[str(p) for p in saidas.values()],
        extra={"ano_pib": args.ano_pib, "ano_pop": args.ano_pop,
               "ano_vab_efetivo": ano_vab_efetivo},
    )
    print(f"[OK] {len(saidas)} arquivos brutos gravados em data/raw/ibge/")
    print(f"     VAB setorial efetivo: {ano_vab_efetivo}")


if __name__ == "__main__":
    main()
