"""
download_censo_estabelecimentos.py — estabelecimentos agropecuários do Censo 2017 por
município, com o SÍMBOLO original de cada célula (SIDRA 6778).

Por que um coletor à parte: o download_censo_agro.py grava o valor já limpo, e a limpeza
(common.clean_num) leva o "-" do IBGE (zero absoluto) e o "X" (sigilo, para não
identificar o estabelecimento) ao mesmo vazio. Para o domínio Produtores do painel, zero
e sigilo não podem se confundir: zero é medida, sigilo é "sem dado publicado".

Baixa, para as 27 UFs, as duas aberturas da tabela 6778:
  atividade   grupos de atividade econômica (lavoura temporária, pecuária, florestal…)
  tipologia   agricultura familiar (sim, não, Pronaf B, Pronaf V, não pronafiano, Pronamp)
e guarda a resposta da API como veio, em <brutos>/censo_agro/estabelecimentos_6778/
(<abertura>_<UF>.json), com manifesto e sha256. Rede só na máquina do usuário.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import (ESTADOS_COD, IBGE2UF, RAW_DIR, SidraClient, require_local_network,  # noqa: E402
                    sha256_file, write_manifest)

TABELA = 6778
ANO = 2017
DESTINO = RAW_DIR / "censo_agro" / "estabelecimentos_6778"
# abertura → termo do nome da classificação nos metadados
ABERTURAS = {"atividade": "grupos de atividade econômica", "tipologia": "tipologia"}
VARIAVEL = "número de estabelecimentos"


def _classif(meta: dict, termo: str) -> str:
    for c in meta.get("classificacoes", []):
        if termo in str(c.get("nome", "")).lower():
            return f"c{c['id']}"
    raise SystemExit(f"classificação '{termo}' não está nos metadados da tabela {TABELA}")


def _variavel(meta: dict) -> str:
    for v in meta.get("variaveis", []):
        if str(v.get("nome", "")).lower().startswith(VARIAVEL):
            return str(v["id"])
    raise SystemExit(f"variável '{VARIAVEL}' não está nos metadados da tabela {TABELA}")


def main():
    require_local_network("Censo Agro 2017 / SIDRA 6778")
    cli = SidraClient()
    meta = cli.metadados(TABELA)
    var = _variavel(meta)
    DESTINO.mkdir(parents=True, exist_ok=True)
    arquivos, linhas = [], 0
    for ab, termo in ABERTURAS.items():
        cl = _classif(meta, termo)
        for cod in ESTADOS_COD:
            uf = IBGE2UF[str(cod).zfill(2)]
            alvo = DESTINO / f"{ab}_{uf}.json"
            if not alvo.exists():
                dados = cli.valores_municipais(TABELA, var, cod, ANO, cl)
                if not dados or len(dados) < 2:
                    raise SystemExit(f"SIDRA não devolveu {ab} de {uf}: rode de novo (retoma do que já baixou)")
                alvo.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
                time.sleep(cli.pause)
            n = len(json.loads(alvo.read_text(encoding="utf-8"))) - 1
            linhas += n
            arquivos.append(str(alvo))
            print(f"  {ab} {uf}: {n:,} linhas")
    write_manifest("raw_censo_estabelecimentos_6778",
                   source=f"IBGE — Censo Agropecuário {ANO}, SIDRA {TABELA} (variável {var})",
                   reference_date=f"{ANO}-09-30", source_files=[], row_count=linhas,
                   output_files=arquivos,
                   extra={"aberturas": ABERTURAS, "simbolos": {"-": "zero absoluto", "X": "sigilo",
                                                              "..": "não se aplica", "...": "não disponível"},
                          "sha256": {Path(a).name: sha256_file(a) for a in arquivos}})
    print(f"[CENSO 6778] {len(arquivos)} arquivos, {linhas:,} linhas em {DESTINO}")


if __name__ == "__main__":
    main()
