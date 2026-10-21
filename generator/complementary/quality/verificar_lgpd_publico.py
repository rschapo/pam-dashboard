"""
verificar_lgpd_publico.py — varre public/ atrás de qualquer coisa que identifique pessoa.

Regra do painel público (decisão do usuário de 21/10/2026, opção A): produtores rurais só
em contagens anônimas por município. Este verificador acusa, em public/:
  - CNPJ, com ou sem máscara (14 dígitos sem dígito nem ponto colado: as casas decimais
    das coordenadas da malha não contam);
  - telefone com DDD entre parênteses ou celular com hífen;
  - "@" nos JSON de public/data (o index.html e o css têm @media e leaflet@ legítimos);
  - chaves de identificação (nome, razao_social, cpf, cnpj, tel, email, endereco, cep, lat,
    lon) nos JSON de produtores e de contas-chave;
  - nomes de produtores pessoa física de uma amostra da base local (fora do OneDrive),
    por frase inteira, sem acento e sem caixa.
Os testes (tests/test_lgpd_publico.py) chamam estas funções; rodar este arquivo direto
imprime o que achar e sai com código 1 se achar algo.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

PUBLIC = Path(__file__).resolve().parents[3] / "public"
TEXTO = {".json", ".js", ".html", ".css", ".txt", ".csv", ".svg", ".md", ".xml"}
ARQUIVOS_PESSOAIS = ("produtores", "contas_chave")   # nomes de arquivo com o que exige vigilância das chaves
CHAVES_PROIBIDAS = {"nome", "razao_social", "cpf", "cnpj", "tel", "telefone", "email", "e-mail",
                    "endereco", "logradouro", "cep", "lat", "lon", "fantasia"}
PALAVRAS_PROPRIEDADE = {"SITIO", "FAZENDA", "CHACARA", "ESTANCIA", "RANCHO", "GRANJA", "HARAS",
                        "AGROPECUARIA", "AGRICOLA", "PECUARIA", "AGRO", "SITIOS", "FAZENDAS", "CHACARAS",
                        "RECANTO", "ESTANCIAS", "GLEBA", "LOTE", "LOTES", "AGROPASTORIL", "SEMENTES",
                        "ESPOLIO", "CONDOMINIO", "CAFE", "CANA", "LEITE", "AVICOLA", "SUINOS"}

RE_CNPJ_MASCARA = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
RE_CNPJ_PURO = re.compile(r"(?<![\d.])\d{14}(?![\d.])")
RE_TELEFONE = re.compile(r"\(\d{2}\)\s*9?\d{4}-?\d{4}|(?<![\d-])9\d{4}-\d{4}(?![\d-])")


def norm(s: str) -> str:
    """Maiúsculas sem acento; o resto fica como está (para achar frase inteira)."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").upper()


def arquivos_texto(raiz: Path = PUBLIC):
    return sorted(p for p in raiz.rglob("*") if p.is_file() and p.suffix.lower() in TEXTO)


def achar_padroes(path: Path) -> list[str]:
    t = path.read_text(encoding="utf-8", errors="ignore")
    achados = [f"CNPJ {m}" for m in RE_CNPJ_MASCARA.findall(t)]
    achados += [f"CNPJ {m}" for m in RE_CNPJ_PURO.findall(t)]
    achados += [f"telefone {m}" for m in RE_TELEFONE.findall(t)]
    if path.suffix.lower() == ".json" and "@" in t:
        achados.append("@ num JSON de dados")
    return achados


def chaves_proibidas(obj, caminho="") -> list[str]:
    """Chaves de identificação em qualquer nível do JSON."""
    achados = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in CHAVES_PROIBIDAS:
                achados.append(f"{caminho}/{k}")
            achados += chaves_proibidas(v, f"{caminho}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:50]):          # listas longas são de números: amostra basta
            achados += chaves_proibidas(v, f"{caminho}[{i}]")
    return achados


def arquivos_pessoais(raiz: Path = PUBLIC):
    return sorted(p for p in (raiz / "data").glob("*.json") if any(n in p.name for n in ARQUIVOS_PESSOAIS))


def amostra_nomes(base_parquet: Path, n: int = 500, seed: int = 20261021, excluir: set[str] | None = None) -> list[str]:
    """Nomes de pessoa (produtor rural PF) sorteados da base local: sem dígitos, com
    duas palavras ou mais, sem palavra de propriedade e sem coincidir com um nome de
    lugar da lista `excluir` (municípios)."""
    import pandas as pd
    b = pd.read_parquet(base_parquet, columns=["tipo", "razao_social"])
    nomes = (b.loc[b["tipo"] == "PF", "razao_social"].dropna().map(norm)
               .str.replace(r"[^A-Z ]", " ", regex=True).str.split().str.join(" "))
    nomes = nomes[nomes.str.count(" ") >= 1].drop_duplicates()
    ok = ~nomes.map(lambda s: bool(set(s.split()) & PALAVRAS_PROPRIEDADE))
    if excluir:
        ok &= ~nomes.isin(excluir)
    nomes = nomes[ok]
    return nomes.sample(min(n, len(nomes)), random_state=seed).tolist()


def achar_nomes(nomes: list[str], arquivos) -> dict[str, list[str]]:
    """Frase inteira (sem letra ou dígito colado) em cada arquivo, sem acento e sem caixa.
    Filtra primeiro pelas palavras: só procura a frase onde todas elas existem."""
    achados: dict[str, list[str]] = {}
    for p in arquivos:
        t = norm(p.read_text(encoding="utf-8", errors="ignore"))
        palavras = set(re.findall(r"[A-Z]+", t))
        for nome in nomes:
            if not set(nome.split()) <= palavras:
                continue
            for m in re.finditer(r"(?<![A-Z0-9])" + re.escape(nome) + r"(?![A-Z0-9])", t):
                achados.setdefault(str(p), []).append(nome)
                break
    return achados


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    erros = []
    for p in arquivos_texto():
        erros += [f"{p.relative_to(PUBLIC)}: {a}" for a in achar_padroes(p)]
    for p in arquivos_pessoais():
        erros += [f"{p.relative_to(PUBLIC)}: chave {c}" for c in
                  chaves_proibidas(json.loads(p.read_text(encoding="utf-8")))]
    print("\n".join(erros) or "public/: nenhum padrão de identificação encontrado")
    sys.exit(1 if erros else 0)


if __name__ == "__main__":
    main()
