"""
download_ibge_areas.py — Baixa as Áreas Territoriais oficiais do IBGE e normaliza
para data/raw/ibge/areas_municipios.csv (cod_ibge;area_km2).

Descobre o arquivo mais recente no diretório oficial do IBGE (não inventa endpoint:
lista o índice e escolhe o AR_BR_MUN mais novo). Fecha a lacuna de area_municipal_ha
no dim_municipio automaticamente. Roda na máquina do usuário (rede aberta).

Uso:
  python download_ibge_areas.py
"""
from __future__ import annotations

import re
import sys
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import RAW_DIR, cod_mun7, write_manifest, today_iso, require_local_network  # noqa: E402

BASE = ("https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/"
        "areas_territoriais/")
UA = {"User-Agent": "AgrocoreEstudos/1.0 (bases complementares)"}


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def _links(url: str) -> list[str]:
    html = _get(url).decode("utf-8", "replace")
    return re.findall(r'href="([^"?][^"]*)"', html)


def descobrir_arquivo() -> str:
    """Retorna a URL do arquivo AR_BR_MUN mais recente (nível município)."""
    top = _links(BASE)
    # subpastas por ano (ex.: '2024/'); pega a mais nova
    anos = sorted({l.strip("/") for l in top if re.fullmatch(r"\d{4}/?", l)}, reverse=True)
    candidatos_dirs = [BASE + a + "/" for a in anos] + [BASE]
    padrao = re.compile(r"AR.*MUN.*\.(xlsx|xls|ods)$", re.I)
    for d in candidatos_dirs:
        try:
            for l in _links(d):
                if padrao.search(l):
                    return d + l
        except Exception:
            continue
    raise SystemExit("Não encontrei o arquivo AR_BR_MUN no índice do IBGE. "
                     "Baixe manualmente para data/raw/ibge/areas_municipios.xlsx.")


def normalizar(path_local: Path) -> pd.DataFrame:
    ext = path_local.suffix.lower()
    engine = {".xlsx": "openpyxl", ".xls": "xlrd", ".ods": "odf"}.get(ext)
    # header pode ter linhas de título; tenta detectar a linha do cabeçalho
    for hdr in (0, 1, 2, 3):
        try:
            df = pd.read_excel(path_local, engine=engine, header=hdr, dtype=str)
        except Exception as e:
            if hdr == 3:
                raise SystemExit(f"Falha ao ler {path_local.name}: {e}\n"
                                 "Instale o leitor: pip install xlrd odfpy (para .xls/.ods)")
            continue
        cols = list(df.columns)
        c_cod = next((c for c in cols if re.search(r"cd.*mun|cod.*mun|geoc", str(c), re.I)
                      and "uf" not in str(c).lower()), None)
        c_area = next((c for c in cols if re.search(r"ar.*mun|area", str(c), re.I)), None)
        if c_cod and c_area:
            def _num(x):
                s = str(x).strip()
                return s.replace(".", "").replace(",", ".") if "," in s else s
            out = pd.DataFrame({
                "cod_ibge": df[c_cod].map(cod_mun7),
                "area_km2": pd.to_numeric(df[c_area].map(_num), errors="coerce"),
            }).dropna(subset=["cod_ibge"])
            return out[out["cod_ibge"].notna()]
    raise SystemExit(f"Colunas de código/área não reconhecidas em {path_local.name}.")


def main():
    require_local_network("IBGE Áreas")
    dst = RAW_DIR / "ibge"
    dst.mkdir(parents=True, exist_ok=True)
    url = descobrir_arquivo()
    print(f"[ÁREAS] fonte: {url}")
    bruto = dst / url.split("/")[-1]
    bruto.write_bytes(_get(url))
    df = normalizar(bruto)
    out = dst / "areas_municipios.csv"
    df.to_csv(out, sep=";", index=False, encoding="utf-8")
    write_manifest("raw_ibge_areas", source="IBGE — Áreas Territoriais",
                   reference_date=today_iso(), source_files=[str(bruto)],
                   output_files=[str(out)], row_count=len(df),
                   municipality_count=df["cod_ibge"].nunique())
    print(f"[ÁREAS] {len(df):,} municípios -> {out.name} (bruto: {bruto.name})")


if __name__ == "__main__":
    main()
