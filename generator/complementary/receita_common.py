"""
receita_common.py — o que as etapas da base CNPJ da Receita Federal compartilham
(contas-chave e produtores rurais).

  * período vigente da base (PERIODO_ATUAL.txt) e conexão DuckDB SÓ LEITURA;
  * pasta do cache de dado pessoal (`pf_cache_dir`): a base com identificador
    (CNPJ, razão social de produtor pessoa física) fica fora do OneDrive e fora do
    projeto, e a função recusa qualquer caminho que caia num dos dois;
  * casamento do município da Receita (código próprio + nome) com o código IBGE,
    por (nome normalizado, UF) sobre os VALORES DISTINTOS, nunca linha a linha;
  * classificação da natureza jurídica em PF (4120, produtor rural pessoa física),
    PJ (2xxx, entidades empresariais) e outra.

Base: Dados Abertos CNPJ, banco cnpj_<período>.duckdb montado pelos scripts da pasta
"Dados Receita Federal" (tudo texto, layout oficial). Regras de uso no LEIA-ME de lá:
memory_limit 20 GB, temp_directory fora do OneDrive, sem índice ART, sem ORDER BY
dentro de string_agg.
"""
from __future__ import annotations

import csv
import os
import re
import unicodedata
from pathlib import Path

from common import ALIASES_MUNICIPIO, DATA_DIR, PROCESSED_DIR, PROJECT_ROOT

CNPJ_DIR = Path(os.environ.get("RFB_CNPJ_DIR", r"D:\00-Claude_Fora_Drive\Dados Receita Federal\CNPJ"))
DUCKDB_TMP = Path(os.environ.get("RFB_DUCKDB_TMP", r"D:\00-Claude_Fora_Drive\pam-dashboard\duckdb_tmp"))
CACHE_PADRAO = Path(r"D:\00-Claude_Fora_Drive\pam-dashboard\receita_cache")
CONFIG_DIR = Path(__file__).resolve().parent / "config"
ALIASES_RFB_CSV = CONFIG_DIR / "aliases_municipio_rfb.csv"


def periodo_atual() -> str:
    return (CNPJ_DIR / "PERIODO_ATUAL.txt").read_text(encoding="utf-8").strip()


def conectar(periodo: str | None = None):
    """Banco do período, só leitura. O import é tardio: os testes não precisam do DuckDB."""
    import duckdb
    per = periodo or periodo_atual()
    banco = CNPJ_DIR / f"cnpj_{per}.duckdb"
    if not banco.exists():
        raise SystemExit(f"Banco CNPJ ausente: {banco}")
    DUCKDB_TMP.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(banco), read_only=True)
    con.execute("PRAGMA threads=8")
    con.execute("PRAGMA memory_limit='20GB'")
    con.execute(f"SET temp_directory='{DUCKDB_TMP.as_posix()}'")
    return con


# ──────────────────────────────────────────────────────────────────────────────
# Cache de dado pessoal
# ──────────────────────────────────────────────────────────────────────────────
def _proibido(p: Path) -> str | None:
    """Motivo para recusar a pasta, ou None se ela serve."""
    p = p.resolve()
    raiz = PROJECT_ROOT.resolve()
    if p == raiz or raiz in p.parents:
        return "fica dentro do projeto (iria para o git ou para public/)"
    if any("onedrive" in parte.lower() for parte in p.parts):
        return "fica dentro do OneDrive (sincroniza dado pessoal para a nuvem)"
    return None


def pf_cache_dir(criar: bool = True) -> Path:
    """Pasta da base com identificador. PAM_CACHE_PF, ou o caminho em
    data/cache_pf_dir.txt, ou o padrão fora do OneDrive. Aborta se a pasta cair no
    projeto ou no OneDrive: a regra de dado pessoal não admite exceção."""
    env = os.environ.get("PAM_CACHE_PF")
    ponteiro = DATA_DIR / "cache_pf_dir.txt"
    if env:
        p = Path(env).expanduser()
    elif ponteiro.exists():
        p = Path(ponteiro.read_text(encoding="utf-8").strip()).expanduser()
    else:
        p = CACHE_PADRAO
    motivo = _proibido(p)
    if motivo:
        raise SystemExit(f"Cache de dado pessoal recusado ({p}): {motivo}.")
    if criar:
        p.mkdir(parents=True, exist_ok=True)
    return p


def pf_cache_existente() -> Path | None:
    """A pasta do cache, se já existe (para os testes, que não criam nada)."""
    try:
        p = pf_cache_dir(criar=False)
    except SystemExit:
        return None
    return p if p.exists() else None


# ──────────────────────────────────────────────────────────────────────────────
# Natureza jurídica
# ──────────────────────────────────────────────────────────────────────────────
TIPOS = {
    "PF": "Produtor rural pessoa física (natureza 4120)",
    "PJ": "Pessoa jurídica empresarial (natureza 2xxx, inclui cooperativas)",
    "outra": "Outras naturezas (associações, órgãos públicos e demais)",
}


def tipo_natureza(nat) -> str:
    s = str(nat or "").strip()
    if s == "4120":
        return "PF"
    if s.startswith("2"):
        return "PJ"
    return "outra"


def capital_reais(txt) -> float | None:
    """Capital social da Receita vem como texto pt-BR ("1.234.567,89")."""
    if txt is None:
        return None
    s = str(txt).strip()
    if not s:
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Município da Receita → IBGE
# ──────────────────────────────────────────────────────────────────────────────
def chave_nome(s) -> str:
    """Sem acento, sem caixa e só letras e dígitos: "Guajará-Mirim", "GUAJARA MIRIM"
    e "D'Oeste"/"D OESTE" caem na mesma chave."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def _aliases() -> dict[tuple[str, str], str]:
    """(chave do nome na fonte, UF) → chave do nome no IBGE. Junta os aliases que o
    projeto já usa (MapBiomas, SICOR) aos da Receita, revisados em
    config/aliases_municipio_rfb.csv (nome_rfb;uf;nome_ibge)."""
    out = {}
    for fonte, ibge in ALIASES_MUNICIPIO.items():
        nf, uf = fonte.split("|")
        ni, _ = ibge.split("|")
        out[(chave_nome(nf), uf)] = chave_nome(ni)
    if ALIASES_RFB_CSV.exists():
        with open(ALIASES_RFB_CSV, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh, delimiter=";"):
                out[(chave_nome(r["nome_rfb"]), r["uf"].strip())] = chave_nome(r["nome_ibge"])
    return out


def indice_ibge(dim=None) -> dict[tuple[str, str], str]:
    """(chave do nome, UF) → código IBGE de 7 dígitos, da dim_municipio."""
    import pandas as pd
    if dim is None:
        dim = pd.read_parquet(PROCESSED_DIR / "dimensions" / "dim_municipio.parquet",
                              columns=["cod_municipio", "nome_municipio", "uf"])
    idx = {}
    for cod, nome, uf in zip(dim.cod_municipio.astype(str), dim.nome_municipio, dim.uf):
        idx[(chave_nome(nome), uf)] = cod
    return idx


def casar_municipios(pares, dim=None) -> tuple[dict, list]:
    """Recebe os pares DISTINTOS (nome do município na Receita, UF) e devolve
    ({(nome, uf): cod_ibge}, [pares sem casamento]). Uma consulta por par, e não por
    estabelecimento: são ~5,6 mil pares contra milhões de linhas."""
    idx = indice_ibge(dim)
    ali = _aliases()
    mapa, sem = {}, []
    for nome, uf in pares:
        k = chave_nome(nome)
        cod = idx.get((k, uf)) or idx.get((ali.get((k, uf), ""), uf))
        if cod:
            mapa[(nome, uf)] = cod
        else:
            sem.append((nome, uf))
    return mapa, sorted(sem, key=lambda x: (x[1] or "", x[0] or ""))
