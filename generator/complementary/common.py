"""
common.py — utilitários compartilhados pelos pipelines das bases complementares
(fundiárias, produtivas e ambientais) do projeto Dashboard Agrocore.

Mantém em um só lugar o que os scripts de download/process/quality reutilizam,
para ficarem em sintonia com os geradores já existentes (generator/process_pam.py,
generator/process_pevs.py, scripts/coletar_base.py da Base_Municipios_Brasil):

  * mapas UF (código IBGE de 2 díg → sigla → nome → grande região);
  * normalização do código municipal como TEXTO de 7 dígitos;
  * limpeza de valores numéricos vindos da SIDRA ("-", "..", "X" → None);
  * cliente SIDRA com descoberta de metadados (mesma abordagem robusta do
    download_pevs_ibge.py — variáveis/classificações NÃO ficam fixas no código);
  * escrita de manifesto + hash SHA-256 para rastreabilidade;
  * constantes de projeção (SIRGAS 2000 EPSG:4674 p/ armazenamento; EPSG:5880 p/ área).

NENHUMA rede é chamada na importação. Os coletores só tocam a internet quando
executados na máquina do usuário (o IBGE/Incra/SICAR não são alcançáveis em
ambientes com allowlist de rede fechada).
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Caminhos-padrão do projeto (resolvidos a partir deste arquivo)
# ──────────────────────────────────────────────────────────────────────────────
# .../pam-dashboard/generator/complementary/common.py  →  raiz = pam-dashboard
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


def _resolver_raw() -> Path:
    """Onde ficam os dados brutos.

    O CAR sozinho passa de 20 GB e o projeto vive numa pasta sincronizada, onde
    esse volume não cabe. Por isso o bruto pode morar fora da árvore do projeto:
    PAM_RAW_DIR no ambiente, ou o caminho escrito em data/raw_dir.txt. Sem
    nenhum dos dois, segue em data/raw como antes.
    """
    env = os.environ.get("PAM_RAW_DIR")
    if env:
        return Path(env).expanduser()
    ponteiro = DATA_DIR / "raw_dir.txt"
    if ponteiro.exists():
        destino = Path(ponteiro.read_text(encoding="utf-8").strip()).expanduser()
        if destino.is_absolute():
            return destino
    return DATA_DIR / "raw"


RAW_DIR = _resolver_raw()
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
MANIFEST_DIR = DATA_DIR / "manifests"
CONFIG_DIR = Path(__file__).resolve().parent / "config"

# Convenções de saída (alinhadas ao DICIONARIO_DE_DADOS.md da base-mestra)
CSV_SEP = ";"          # ponto-e-vírgula
CSV_ENCODING = "utf-8" # UTF-8; decimal com ponto
NULL_TOKEN = ""        # ausência = campo vazio no CSV / null no parquet

# Projeções cartográficas
CRS_STORAGE = "EPSG:4674"   # SIRGAS 2000 (geográfica) — armazenamento
CRS_AREA = "EPSG:5880"      # SIRGAS 2000 / Brazil Polyconic — cálculo de área

# ──────────────────────────────────────────────────────────────────────────────
# Tabelas UF (código IBGE 2 díg ↔ sigla ↔ nome ↔ região)
# ──────────────────────────────────────────────────────────────────────────────
IBGE2UF = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP",
    "41": "PR", "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}
UF2IBGE = {v: k for k, v in IBGE2UF.items()}

UF_NAMES = {
    "RO": "Rondônia", "AC": "Acre", "AM": "Amazonas", "RR": "Roraima", "PA": "Pará",
    "AP": "Amapá", "TO": "Tocantins", "MA": "Maranhão", "PI": "Piauí", "CE": "Ceará",
    "RN": "Rio Grande do Norte", "PB": "Paraíba", "PE": "Pernambuco", "AL": "Alagoas",
    "SE": "Sergipe", "BA": "Bahia", "MG": "Minas Gerais", "ES": "Espírito Santo",
    "RJ": "Rio de Janeiro", "SP": "São Paulo", "PR": "Paraná", "SC": "Santa Catarina",
    "RS": "Rio Grande do Sul", "MS": "Mato Grosso do Sul", "MT": "Mato Grosso",
    "GO": "Goiás", "DF": "Distrito Federal",
}

# Grande região: nome e código IBGE (1 díg)
UF_REGION_NAME = {
    "RO": "Norte", "AC": "Norte", "AM": "Norte", "RR": "Norte", "PA": "Norte",
    "AP": "Norte", "TO": "Norte",
    "MA": "Nordeste", "PI": "Nordeste", "CE": "Nordeste", "RN": "Nordeste",
    "PB": "Nordeste", "PE": "Nordeste", "AL": "Nordeste", "SE": "Nordeste", "BA": "Nordeste",
    "MG": "Sudeste", "ES": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
    "PR": "Sul", "SC": "Sul", "RS": "Sul",
    "MS": "Centro-Oeste", "MT": "Centro-Oeste", "GO": "Centro-Oeste", "DF": "Centro-Oeste",
}
REGION_NAME2COD = {
    "Norte": "1", "Nordeste": "2", "Sudeste": "3", "Sul": "4", "Centro-Oeste": "5",
}
UFS = list(UF_NAMES.keys())
ESTADOS_COD = [int(UF2IBGE[uf]) for uf in UFS]

# ──────────────────────────────────────────────────────────────────────────────
# Normalização / limpeza
# ──────────────────────────────────────────────────────────────────────────────
def cod_mun7(value) -> str | None:
    """Normaliza qualquer representação de código municipal para TEXTO de 7 dígitos.
    Aceita int, float, str (com/sem zeros à esquerda). Retorna None se inválido."""
    if value is None:
        return None
    s = str(value).strip()
    if s in ("", "nan", "None"):
        return None
    # remove parte decimal de floats tipo "1100015.0"
    if s.endswith(".0"):
        s = s[:-2]
    s = "".join(ch for ch in s if ch.isdigit())
    if not s:
        return None
    # Códigos municipais do IBGE têm 7 dígitos e começam por 11–53 (UF), nunca 0.
    # Não fazemos zfill: um "35" (UF) jamais deve virar "0000035" (município falso).
    return s if len(s) == 7 else None


def uf_from_cod(cod_mun) -> str | None:
    """Deriva a sigla UF pelos 2 primeiros dígitos do código municipal (7 díg)."""
    c = cod_mun7(cod_mun)
    if not c:
        return None
    return IBGE2UF.get(c[:2])


# tokens que a SIDRA usa para "sem informação"/sigiloso
_SIDRA_NULLS = {"-", "..", "...", "x", "X", "", "nd", "ND", "-0", "..."}


def clean_num(value):
    """Converte texto SIDRA em float; devolve None para nulos/sigilosos.
    NUNCA transforma ausência em zero (regra 4.2 do briefing)."""
    if value is None:
        return None
    s = str(value).strip()
    if s in _SIDRA_NULLS:
        return None
    s = s.replace(".", "").replace(",", ".") if _looks_ptbr_number(s) else s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _looks_ptbr_number(s: str) -> bool:
    """Heurística: '1.234,56' (pt-BR) vs '1234.56' (en). Usada só em clean_num."""
    return ("," in s) and (s.rfind(",") > s.rfind("."))


# ──────────────────────────────────────────────────────────────────────────────
# Hash + manifesto (rastreabilidade — seção 2.2 / 8 do briefing)
# ──────────────────────────────────────────────────────────────────────────────
def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def today_iso() -> str:
    return datetime.now(timezone.utc).astimezone().date().isoformat()


def write_manifest(dataset: str, *, source: str, reference_date: str | None,
                   source_files: list[str] | None = None,
                   row_count: int = 0, municipality_count: int = 0,
                   rejected_rows: int = 0, warnings: list[str] | None = None,
                   output_files: list[str] | None = None,
                   script_version: str = "0.1.0",
                   extra: dict | None = None) -> Path:
    """Grava data/manifests/<dataset>.json com metadados + hashes das fontes."""
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    src_files = source_files or []
    src_hashes = []
    for f in src_files:
        try:
            src_hashes.append({"file": os.path.basename(f), "sha256": sha256_file(f)})
        except OSError:
            src_hashes.append({"file": os.path.basename(f), "sha256": None})
    out_files = output_files or []
    out_meta = []
    for f in out_files:
        try:
            out_meta.append({"file": os.path.basename(f),
                             "sha256": sha256_file(f),
                             "bytes": os.path.getsize(f)})
        except OSError:
            out_meta.append({"file": os.path.basename(f), "sha256": None, "bytes": None})

    manifest = {
        "dataset": dataset,
        "source": source,
        "extraction_date": today_iso(),
        "reference_date": reference_date,
        "source_files": [os.path.basename(f) for f in src_files],
        "source_hashes": src_hashes,
        "script_version": script_version,
        "row_count": int(row_count),
        "municipality_count": int(municipality_count),
        "rejected_rows": int(rejected_rows),
        "warnings": warnings or [],
        "output_files": out_meta,
        "generated_at": now_iso(),
    }
    if extra:
        manifest.update(extra)
    out = MANIFEST_DIR / f"{dataset}.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def update_global_manifest():
    """Reúne todos os data/manifests/*.json em complementary_data_manifest.json."""
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    datasets = []
    for p in sorted(MANIFEST_DIR.glob("*.json")):
        if p.name == "complementary_data_manifest.json":
            continue
        try:
            datasets.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    doc = {"generated_at": now_iso(), "n_datasets": len(datasets), "datasets": datasets}
    out = MANIFEST_DIR / "complementary_data_manifest.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


# ──────────────────────────────────────────────────────────────────────────────
# IO de tabelas (CSV de conferência + Parquet analítico)
# ──────────────────────────────────────────────────────────────────────────────
def save_table(df, path_no_ext: str | Path, *, csv=True, parquet=True) -> list[str]:
    """Grava um DataFrame como .parquet (analítico) e .csv (conferência, sep=';')."""
    path_no_ext = Path(path_no_ext)
    path_no_ext.parent.mkdir(parents=True, exist_ok=True)
    outs = []
    if parquet:
        p = path_no_ext.with_suffix(".parquet")
        df.to_parquet(p, index=False)
        outs.append(str(p))
    if csv:
        c = path_no_ext.with_suffix(".csv")
        df.to_csv(c, sep=CSV_SEP, index=False, encoding=CSV_ENCODING)
        outs.append(str(c))
    return outs


# ──────────────────────────────────────────────────────────────────────────────
# Cliente SIDRA (rede só na máquina do usuário) — descoberta de metadados
# ──────────────────────────────────────────────────────────────────────────────
API_META = "https://servicodados.ibge.gov.br/api/v3/agregados"
API_SIDRA = "https://apisidra.ibge.gov.br/values"
API_LOCALIDADES = "https://servicodados.ibge.gov.br/api/v1/localidades"


class SidraClient:
    """Cliente fino para a SIDRA. `requests` só é importado no uso, para o módulo
    ser importável em ambiente sem rede (testes, CI, este container Cowork)."""

    def __init__(self, pause: float = 0.8, timeout: int = 90, max_tries: int = 3):
        self.pause = pause
        self.timeout = timeout
        self.max_tries = max_tries

    def _requests(self):
        import requests  # import tardio de propósito
        return requests

    def metadados(self, tabela: int) -> dict:
        requests = self._requests()
        r = requests.get(f"{API_META}/{tabela}/metadados", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def periodos(self, tabela: int) -> list[int]:
        requests = self._requests()
        r = requests.get(f"{API_META}/{tabela}/periodos", timeout=self.timeout)
        r.raise_for_status()
        return sorted(int(p["id"]) for p in r.json() if str(p.get("id", "")).isdigit())

    def descobrir_variaveis(self, meta: dict, metricas: dict[str, str]) -> dict[str, str]:
        """Casa cada métrica pedida (chave→texto) com a variável cujo nome contém o
        texto. Devolve {cod_variavel: metrica}. Igual ao download_pevs_ibge.py."""
        def _norm(s): return s.lower().replace("á", "a").replace("ã", "a").replace("í", "i")
        out = {}
        for metrica, chave in metricas.items():
            alvo = None
            for v in meta.get("variaveis", []):
                if _norm(chave) in _norm(str(v.get("nome", ""))):
                    alvo = str(v.get("id"))
                    break
            if alvo:
                out[alvo] = metrica
        return out

    def valores_municipais(self, tabela: int, variaveis: str, estado_cod: int,
                           periodo, classif: str | None = None) -> list:
        """GET /values/t/{t}/n6/in n3 {uf}/v/{vars}/p/{periodo}[/{classif}/all].
        Nível n6 (município) filtrado por n3 (UF), 1 UF por vez — evita 500/timeout
        em consultas nacionais, mesmo padrão dos coletores PAM/PPM/PEVS."""
        requests = self._requests()
        import time
        classif_path = f"/{classif}/all" if classif else ""
        url = (f"{API_SIDRA}/t/{tabela}/n6/in%20n3%20{estado_cod}"
               f"/v/{variaveis}/p/{periodo}{classif_path}")
        for tent in range(1, self.max_tries + 1):
            try:
                r = requests.get(url, timeout=self.timeout)
                if r.status_code == 400:
                    return []
                if r.status_code == 429:
                    time.sleep(60); continue
                r.raise_for_status()
                return r.json()
            except Exception:
                if tent == self.max_tries:
                    return []
                time.sleep(5 * tent)
        return []

    def mun_to_micro(self) -> dict[str, str]:
        """Mapa município→microrregião via API de localidades (a SIDRA municipal não
        devolve microrregião). Mesma abordagem do process_pevs.py."""
        requests = self._requests()
        r = requests.get(f"{API_LOCALIDADES}/municipios", timeout=60)
        r.raise_for_status()
        return {cod_mun7(m["id"]): str(m["microrregiao"]["id"])
                for m in r.json() if m.get("microrregiao")}


def require_local_network(source_name: str):
    """Falha cedo e com mensagem clara se o coletor for rodado sem rede (allowlist).
    Chame no início de cada main() de download."""
    import socket
    try:
        socket.create_connection(("servicodados.ibge.gov.br", 443), timeout=5).close()
    except OSError:
        raise SystemExit(
            f"[{source_name}] Sem acesso à rede do IBGE/fonte oficial.\n"
            "Os coletores oficiais precisam rodar NA SUA MÁQUINA (rede aberta).\n"
            "Em ambientes com allowlist (Cowork/CI) apenas os passos de PROCESSAMENTO\n"
            "sobre arquivos já baixados em data/raw/ funcionam."
        )
