"""
download_modulo_fiscal.py — Baixa os Índices Básicos do INCRA por município (módulo
fiscal, fração mínima de parcelamento, zona típica de módulo e zona de pecuária).

Os índices em vigor são os da Instrução Especial INCRA nº 5/2022 (DOU de 01/08/2022).
O INCRA não publica a tabela completa em planilha: a página "Módulo Fiscal" do órgão
remete a três peças, todas baixadas aqui para data/raw/incra/:

  indices_basicos_2013_por_municipio.pdf  Índices Básicos de 2013 do SNCR, com o código
                                          IBGE de cada município. Dá o módulo fiscal e a
                                          zona de pecuária, que a IE de 2022 manteve.
  tabela-fmp_alterado.xls                 os municípios cuja fração mínima de
                                          parcelamento a IE de 2022 mudou (1.885).
  ie_incra_5_2022.html                    a IE no DOU. O Anexo III dá a zona típica de cada
                                          região geográfica imediata; o Anexo IV aparece só
                                          até "Butiá" e serve de conferência.

A consulta online do INCRA ("Consultar Índices Básicos") exige CAPTCHA e não é usada.
Se um link mudar, baixe a peça à mão pela página do INCRA e salve com o mesmo nome.
Arquivo já presente não é baixado de novo (use --forcar).

Uso:
  python download_modulo_fiscal.py [--forcar]
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import RAW_DIR, write_manifest, require_local_network  # noqa: E402

PAGINA = "https://www.gov.br/incra/pt-br/assuntos/governanca-fundiaria/modulo-fiscal"
# O DOU recusa (403) requisição sem Accept, que o urllib não manda por conta própria.
UA = {"User-Agent": "AgrocoreEstudos/1.0 (bases complementares)", "Accept": "*/*"}

# nome no raw → (URL, como reconhecer o arquivo certo). O gov.br devolve uma página
# HTML, e não o arquivo, quando o link perde o sufixo @@display-file/@@download.
FONTES = {
    "indices_basicos_2013_por_municipio.pdf": (
        "https://www.gov.br/incra/pt-br/acesso-a-informacao/"
        "indices_basicos_2013_por_municipio.pdf/@@display-file/file",
        lambda b: b.startswith(b"%PDF")),
    "tabela-fmp_alterado.xls": (
        "https://www.gov.br/incra/pt-br/assuntos/noticias/"
        "reclassificacao-de-imoveis-rurais-beneficia-produtores-de-todo-o-pais/"
        "tabela-fmp_alterado.xls/@@download/file",
        lambda b: b.startswith(b"\xd0\xcf\x11\xe0")),   # planilha Excel 97-2003
    "ie_incra_5_2022.html": (
        "https://www.in.gov.br/web/dou/-/instrucao-especial-n-5-de-29-de-julho-de-2022-418986404",
        lambda b: "ANEXO III" in b.decode("utf-8", "replace")),
}


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--forcar", action="store_true", help="baixa de novo o que já existe")
    args = ap.parse_args()

    dst = RAW_DIR / "incra"
    dst.mkdir(parents=True, exist_ok=True)
    faltando = [n for n in FONTES if args.forcar or not (dst / n).exists()]
    if faltando:
        require_local_network("INCRA Índices Básicos")
    falhas = []
    for nome, (url, confere) in FONTES.items():
        alvo = dst / nome
        if nome not in faltando:
            print(f"  {nome}: já presente")
            continue
        try:
            dados = _get(url)
        except Exception as e:  # noqa: BLE001
            falhas.append(f"{nome}: {type(e).__name__}: {e}")
            continue
        if not confere(dados):
            falhas.append(f"{nome}: o link não devolveu o arquivo esperado ({url})")
            continue
        alvo.write_bytes(dados)
        print(f"  {nome}: {len(dados) / 1_048_576:.2f} MB")

    if falhas:
        print("[MÓDULO FISCAL] Falhou:")
        for f in falhas:
            print("  " + f)
        print(f"  Baixe a peça pela página do INCRA ({PAGINA}) e salve em {dst} com o mesmo nome.")
        raise SystemExit(2)

    write_manifest("raw_modulo_fiscal",
                   source="INCRA — Índices Básicos (IE nº 5/2022 e tabela de 2013)",
                   reference_date="2022-08-01",
                   source_files=[str(dst / n) for n in FONTES],
                   output_files=[str(dst / n) for n in FONTES],
                   extra={"urls": {n: u for n, (u, _) in FONTES.items()}, "pagina": PAGINA})
    print(f"[MÓDULO FISCAL] OK — {len(FONTES)} peças em {dst}")


if __name__ == "__main__":
    main()
