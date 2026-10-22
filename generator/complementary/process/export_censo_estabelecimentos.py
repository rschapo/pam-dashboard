"""
export_censo_estabelecimentos.py — gera public/data/censo_estab_mun.json: os
estabelecimentos agropecuários do Censo Agropecuário 2017 por município, por grupo de
atividade e por tipologia (agricultura familiar, Pronaf, Pronamp).

Entra no domínio Produtores do painel como a fonte comparável entre estados. A contagem
da Receita (produtores_mun.json) só vê quem tem CNPJ, e o produtor pessoa física só tem
CNPJ em SP e AL; o Censo recenseia todo estabelecimento, com CPF ou CNPJ, nas 27 UFs.
No RS são 365.094 estabelecimentos, contra 15.646 cadastros na Receita.

Lê a resposta bruta da SIDRA guardada por download_censo_estabelecimentos.py, com o
símbolo de cada célula: "-" é zero, "X" é sigilo (null, nunca zero), ".." e "..." também
ficam null. As duas aberturas (atividade e tipologia) são tabulações separadas do IBGE e
não se cruzam: não há "pecuária familiar" nesta tabela.

Formato: mun: {cod: {"t": total, "a": [9 atividades], "f": [tipologias]}}, na ordem de
"atividades" e "tipologias". Nada aqui depende de rede.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import RAW_DIR, cod_mun7, now_iso, write_public_json  # noqa: E402

PUBLIC_DATA = Path(__file__).resolve().parents[3] / "public" / "data"
BRUTO = RAW_DIR / "censo_agro" / "estabelecimentos_6778"
TOTAL_BRASIL = 5_073_324          # estabelecimentos do Censo 2017 (IBGE, resultados definitivos)

# rótulo do IBGE → (chave do painel, rótulo curto). A ordem é a dos vetores do JSON.
ATIVIDADES = {
    "Produção de lavouras temporárias": ("temp", "Lavouras temporárias"),
    "Horticultura e floricultura": ("horti", "Horticultura e floricultura"),
    "Produção de lavouras permanentes": ("perm", "Lavouras permanentes"),
    "Produção de sementes e mudas certificadas": ("sementes", "Sementes e mudas certificadas"),
    "Pecuária e criação de outros animais": ("pecuaria", "Pecuária e criação de outros animais"),
    "Produção florestal - florestas plantadas": ("flo_plantada", "Florestas plantadas"),
    "Produção florestal - florestas nativas": ("flo_nativa", "Florestas nativas"),
    "Pesca": ("pesca", "Pesca"),
    "Aquicultura": ("aquicultura", "Aquicultura"),
}
TIPOLOGIAS = {
    "Agricultura familiar - sim": ("familiar", "Agricultura familiar"),
    "Agricultura familiar - não": ("nao_familiar", "Não familiar"),
    "Agricultura familiar - Pronaf B": ("pronaf_b", "Familiar, Pronaf B"),
    "Agricultura familiar - Pronaf V": ("pronaf_v", "Familiar, Pronaf V"),
    "Agricultura familiar - não pronafiano": ("nao_pronafiano", "Familiar não pronafiano"),
    "Pronamp - sim": ("pronamp", "Pronamp (médio produtor)"),
    "Pronamp - não": ("nao_pronamp", "Fora do Pronamp"),
}


def valor(simbolo: str):
    """Símbolo da SIDRA → número. "-" é zero absoluto; "X" (sigilo), ".." e "..." ficam
    sem valor (None), nunca zero."""
    s = str(simbolo).strip()
    if s == "-":
        return 0
    try:
        return int(float(s))
    except ValueError:
        return None


def _coluna(cab: dict, nome: str) -> str:
    """Coluna de categoria (D<n>N) cujo cabeçalho é o nome da classificação."""
    for k, v in cab.items():
        if v == nome and k.endswith("N"):
            return k
    raise SystemExit(f"classificação '{nome}' ausente na resposta da SIDRA")


def ler_abertura(linhas: list[dict], classificacao: str, mapa: dict) -> tuple[dict, dict, int]:
    """Uma resposta da SIDRA → ({cod: {chave: valor}}, {cod: total}, nº de células sob sigilo).
    Só as linhas em que as outras classificações estão em Total."""
    cab, dados = linhas[0], linhas[1:]
    col = _coluna(cab, classificacao)
    outras = [k for k, v in cab.items() if k.startswith("D") and k.endswith("N")
              and k not in (col, "D1N", "D2N", "D3N")]
    por_mun, totais, sigilo = {}, {}, 0
    for r in dados:
        if any(r.get(k) != "Total" for k in outras):
            continue
        cod, cat, v = cod_mun7(r.get("D1C")), r.get(col), valor(r.get("V"))
        if v is None and str(r.get("V")).strip() == "X":
            sigilo += 1
        if cat == "Total":
            totais[cod] = v
        elif cat in mapa:
            por_mun.setdefault(cod, {})[mapa[cat][0]] = v
    return por_mun, totais, sigilo


def build_censo(bruto: Path = BRUTO) -> dict:
    arqs = {ab: sorted(bruto.glob(f"{ab}_*.json")) for ab in ("atividade", "tipologia")}
    if len(arqs["atividade"]) != 27 or len(arqs["tipologia"]) != 27:
        raise SystemExit(f"faltam brutos em {bruto}: rode download/download_censo_estabelecimentos.py")
    ativ, tipo, total, sigilo = {}, {}, {}, 0
    for f in arqs["atividade"]:
        p, t, s = ler_abertura(json.loads(f.read_text(encoding="utf-8")), "Grupos de atividade econômica", ATIVIDADES)
        ativ.update(p); total.update(t); sigilo += s
    for f in arqs["tipologia"]:
        p, t, s = ler_abertura(json.loads(f.read_text(encoding="utf-8")), "Tipologia", TIPOLOGIAS)
        tipo.update(p); sigilo += s
        for cod, v in t.items():                # o total das duas aberturas é o mesmo
            if total.get(cod) != v:
                raise SystemExit(f"total de {cod} difere entre atividade ({total.get(cod)}) e tipologia ({v})")
    ka = [k for k, _ in ATIVIDADES.values()]
    kt = [k for k, _ in TIPOLOGIAS.values()]
    mun = {}
    for cod in sorted(total):
        mun[cod] = {"t": total[cod],
                    "a": [ativ.get(cod, {}).get(k) for k in ka],
                    "f": [tipo.get(cod, {}).get(k) for k in kt]}
    return {
        "fonte": "IBGE — Censo Agropecuário 2017, SIDRA 6778 (número de estabelecimentos agropecuários)",
        "ano": 2017,
        "gerado_em": now_iso(),
        "atividades": {k: r for k, r in ATIVIDADES.values()},
        "tipologias": {k: r for k, r in TIPOLOGIAS.values()},
        "celulas_sigilo": sigilo,
        "cautelas": [
            "Estabelecimento agropecuário é a unidade de produção sob uma única administração, recenseada "
            "com CPF ou CNPJ: é a base comparável entre estados.",
            "Retrato de 2017: municípios criados depois e mudanças desde então não aparecem.",
            "A atividade é a predominante do estabelecimento (a que dá mais valor), uma por estabelecimento.",
            "Atividade e tipologia são tabulações separadas do IBGE e não se cruzam.",
        ],
        "mun": mun,
    }


def main():
    obj = build_censo()
    soma = sum(r["t"] or 0 for r in obj["mun"].values())
    if soma != TOTAL_BRASIL:
        raise SystemExit(f"soma municipal {soma:,} ≠ total do Censo {TOTAL_BRASIL:,}")
    p = write_public_json(PUBLIC_DATA / "censo_estab_mun.json", obj)
    print(f"  censo_estab_mun.json: {len(obj['mun']):,} municípios · {soma:,} estabelecimentos · "
          f"{obj['celulas_sigilo']} células sob sigilo · {p.stat().st_size / 1_048_576:.2f} MB")


if __name__ == "__main__":
    main()
