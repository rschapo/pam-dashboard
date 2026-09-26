"""
process_modulo_fiscal.py — dim_modulo_fiscal (Etapa 1, §6.2).

Monta, por município, os índices básicos do INCRA em vigor (Instrução Especial nº
5/2022) a partir das três peças que download_modulo_fiscal.py grava em data/raw/incra/:

  módulo fiscal, zona de pecuária   da tabela de 2013 (PDF). A IE de 2022 os manteve:
                                    nos 1.885 municípios da planilha e nos 814 do trecho
                                    do Anexo IV, os valores de 2022 são os de 2013.
  fração mínima de parcelamento     a da planilha da IE onde ela mudou; senão, a de 2013.
  zona típica de módulo             a da região geográfica imediata do município no Anexo
                                    III (cada região tem uma zona só, art. 4º §4º). A
                                    planilha não serve: há município que mudou de zona sem
                                    mudar a FMP e por isso não está nela. O DF vem sem zona
                                    no Anexo III e fica com a de 2013.

O trecho do Anexo IV que a página do DOU traz, de "Abadia de Goiás" a "Butiá", é
comparado campo a campo com o resultado; divergência vira aviso no manifesto.

A junção é pelo código IBGE que o PDF traz, sem casar nomes. Município da dim_municipio
sem índice no INCRA (instalado depois da tabela de 2013, ou Fernando de Noronha,
distrito estadual) fica sem linha e é listado no manifesto.

Saídas:
  data/processed/dimensions/dim_modulo_fiscal.parquet | .csv
  data/interim/modulo_fiscal/modulo_fiscal_nao_correspondidos.csv
  data/manifests/dim_modulo_fiscal.json
"""
from __future__ import annotations

import html
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import (  # noqa: E402
    RAW_DIR, INTERIM_DIR, PROCESSED_DIR, UF_NAMES, cod_mun7, save_table, write_manifest,
)

CAMPOS = ["cod_municipio", "modulo_fiscal_ha", "fracao_minima_parcelamento_ha",
          "zona_tipica_modulo", "zona_pecuaria", "data_referencia", "fonte", "observacao"]
DATA_REFERENCIA = "2022-08-01"   # DOU da IE nº 5/2022, em vigor desde a publicação
FONTE = "INCRA — Índices Básicos (IE nº 5/2022; tabela de 2013)"
PDF_2013 = "indices_basicos_2013_por_municipio.pdf"
XLS_2022 = "tabela-fmp_alterado.xls"
HTML_IE = "ie_incra_5_2022.html"

_NUM = r"\d+(?:,\d+)?"
_UF = "|".join(UF_NAMES)
# Linha da tabela de 2013: código IBGE, nome, microrregião, zona de pecuária, módulo
# fiscal, zona típica da IE 50/97 com o número de ordem da zona (A1-1, A2-2 ... C2-8),
# fração mínima, limite para estrangeiro e a situação cadastral, que não é usada.
_LINHA_2013 = re.compile(
    rf"^\s*(?P<cod>\d{{7}})\s+(?P<nome>.+?)\s+\d{{3}}\s+(?P<zp>\d)\s+(?P<mf>{_NUM})\s+"
    rf"(?P<ztm>[A-D]\d?)-\d+\s+(?P<fmp>{_NUM})\s+{_NUM}(?:\s|$)")
# Anexo III: UF, região imediata, código da região, zona típica, FMP e limite para
# estrangeiro. O DF vem sem zona típica.
_RGI = re.compile(rf"\b(?:{_UF}) [^\d]+? (?P<rgi>\d{{6}}) (?:(?P<ztm>[A-D]\d?) )?{_NUM} {_NUM}\b")
# Anexo IV: município, UF, zona típica, zona de pecuária, módulo fiscal, FMP, módulo de
# exploração indefinida, código IBGE e código da região imediata.
_LINHA_IV = re.compile(
    rf"\b(?:{_UF}) (?P<ztm>[A-D]\d?) (?P<zp>\d) (?P<mf>{_NUM}) (?P<fmp>{_NUM}) {_NUM} "
    rf"(?P<cod>\d{{7}}) \d{{6}}\b")


def _num(s) -> float:
    return float(str(s).strip().replace(",", "."))


def _norm(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFKD", str(s)) if not unicodedata.combining(c))
    return s.strip().lower()


def ler_linha_2013(linha: str) -> dict | None:
    m = _LINHA_2013.match(linha)
    if not m:
        return None
    return {"cod_municipio": m["cod"], "nome_incra": m["nome"].strip(),
            "zona_pecuaria": int(m["zp"]), "modulo_fiscal_ha": _num(m["mf"]),
            "ztm_2013": m["ztm"], "fmp_2013": _num(m["fmp"])}


def ler_tabela_2013(linhas) -> tuple[pd.DataFrame, list[str]]:
    """Os municípios da tabela de 2013 e as linhas que começam por código mas não casam."""
    regs, falhas = [], []
    for linha in linhas:
        if not re.match(r"^\s*\d{7}\s", linha):
            continue
        r = ler_linha_2013(linha)
        if r:
            regs.append(r)
        else:
            falhas.append(linha.strip())
    return pd.DataFrame(regs), falhas


def linhas_do_pdf(path: Path) -> list[str]:
    from pypdf import PdfReader   # só o processamento do PDF precisa dele
    linhas = []
    for pagina in PdfReader(path).pages:
        # o modo layout mantém cada município numa linha; o padrão embaralha as colunas
        linhas += pagina.extract_text(extraction_mode="layout").splitlines()
    return linhas


def ler_planilha_2022(path: Path) -> pd.DataFrame:
    """Municípios com FMP alterada pela IE de 2022, com os valores antigos para conferência."""
    x = pd.read_excel(path, dtype=str)
    x.columns = [str(c).strip() for c in x.columns]
    x = x[x["COD_MUN"].map(cod_mun7).notna()]
    return pd.DataFrame({
        "cod_municipio": x["COD_MUN"].map(cod_mun7),
        "mf": x["MF"].map(_num), "zp": x["ZP"].str.strip().astype(int),
        "fmp_antiga": x["FMP"].map(_num), "fmp": x["NOVA FMP"].map(_num),
        "ztm_antiga": x["ZTM"].str.strip(), "ztm": x["NOVA ZTM"].str.strip(),
    }).reset_index(drop=True)


def texto_do_html(path: Path) -> str:
    t = Path(path).read_text(encoding="utf-8", errors="replace")
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S)
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)))


def ler_ie_2022(texto: str) -> tuple[dict, pd.DataFrame]:
    """Zona típica por região imediata (Anexo III) e o trecho do Anexo IV da página."""
    i3, i4 = texto.find("ANEXO III"), texto.find("ANEXO IV")
    if i3 < 0 or i4 < i3:
        raise SystemExit("Anexos III e IV não encontrados na página da IE nº 5/2022.")
    ztm = {m["rgi"]: m["ztm"] for m in _RGI.finditer(texto[i3:i4])}
    iv = pd.DataFrame([{"cod_municipio": m["cod"], "ztm": m["ztm"], "zp": int(m["zp"]),
                        "mf": _num(m["mf"]), "fmp": _num(m["fmp"])}
                       for m in _LINHA_IV.finditer(texto[i4:])])
    return ztm, iv


def combinar(t13: pd.DataFrame, p22: pd.DataFrame, ztm_rgi: dict, dim: pd.DataFrame):
    """Índices em vigor por município. Devolve a dimensão, as linhas do INCRA sem
    município na dim_municipio, os municípios da dim sem índice e os avisos."""
    avisos = []
    ant = p22.merge(t13, on="cod_municipio", how="left")
    for novo, velho, rotulo in (("mf", "modulo_fiscal_ha", "o módulo fiscal"),
                                ("zp", "zona_pecuaria", "a zona de pecuária"),
                                ("fmp_antiga", "fmp_2013", "a FMP anterior"),
                                ("ztm_antiga", "ztm_2013", "a zona típica anterior")):
        n = int((ant[novo] != ant[velho]).sum())
        if n:
            avisos.append(f"planilha de 2022: {rotulo} difere da tabela de 2013 em {n} municípios")

    df = t13.merge(p22[["cod_municipio", "fmp", "ztm"]], on="cod_municipio", how="left")
    df["fracao_minima_parcelamento_ha"] = df["fmp"].fillna(df["fmp_2013"])
    rgi = dim.set_index("cod_municipio")["cod_regiao_imediata"].astype(str)
    df["zona_tipica_modulo"] = df["cod_municipio"].map(rgi).map(ztm_rgi)
    n = int((df["ztm"].notna() & (df["ztm"] != df["zona_tipica_modulo"])).sum())
    if n:
        avisos.append(f"planilha de 2022: a zona típica difere da do Anexo III em {n} municípios")
    sem_zona = df["zona_tipica_modulo"].isna()
    df["observacao"] = None
    df.loc[sem_zona, "observacao"] = ("zona típica de 2013: o Anexo III da IE nº 5/2022 "
                                      "não a informa para a região imediata")
    df["zona_tipica_modulo"] = df["zona_tipica_modulo"].fillna(df["ztm_2013"])
    df["data_referencia"] = DATA_REFERENCIA
    df["fonte"] = FONTE

    na_dim = df["cod_municipio"].isin(dim["cod_municipio"])
    nao = df.loc[~na_dim, ["cod_municipio", "nome_incra"]].reset_index(drop=True)
    faltam = dim.loc[~dim["cod_municipio"].isin(df["cod_municipio"]),
                     ["cod_municipio", "nome_municipio", "uf"]].reset_index(drop=True)
    return df.loc[na_dim, CAMPOS].reset_index(drop=True), nao, faltam, avisos


def conferir_anexo_iv(df: pd.DataFrame, iv: pd.DataFrame) -> dict:
    """Compara o resultado, campo a campo, com o trecho do Anexo IV da página do DOU."""
    m = iv.merge(df, on="cod_municipio", how="left")
    div = {"ausentes": int(m["modulo_fiscal_ha"].isna().sum())}
    for a, b in (("mf", "modulo_fiscal_ha"), ("fmp", "fracao_minima_parcelamento_ha"),
                 ("ztm", "zona_tipica_modulo"), ("zp", "zona_pecuaria")):
        div[b] = int((m[a] != m[b]).sum())
    return {"municipios": len(iv), "divergencias": div}


def _nomes_diferentes(t13: pd.DataFrame, dim: pd.DataFrame) -> list[str]:
    """Municípios renomeados depois de 2013 (ou grafados de outro jeito pelo INCRA)."""
    m = t13.merge(dim, on="cod_municipio")
    d = m[m["nome_incra"].map(_norm) != m["nome_municipio"].map(_norm)]
    return [f"{r.cod_municipio} {r.nome_incra} → {r.nome_municipio}" for r in d.itertuples()]


def _ler_dim() -> pd.DataFrame:
    p = PROCESSED_DIR / "dimensions" / "dim_municipio.parquet"
    if not p.exists():
        raise SystemExit("dim_municipio ausente. Rode process/process_geography.py primeiro.")
    return pd.read_parquet(p)[["cod_municipio", "nome_municipio", "uf", "cod_regiao_imediata"]]


def main():
    base = RAW_DIR / "incra"
    brutos = [base / n for n in (PDF_2013, XLS_2022, HTML_IE)]
    ausentes = [p.name for p in brutos if not p.exists()]
    if ausentes:
        raise SystemExit(f"Brutos do INCRA ausentes ({', '.join(ausentes)}). "
                         "Rode download/download_modulo_fiscal.py primeiro.")
    dim = _ler_dim()
    t13, falhas = ler_tabela_2013(linhas_do_pdf(base / PDF_2013))
    p22 = ler_planilha_2022(base / XLS_2022)
    ztm_rgi, iv = ler_ie_2022(texto_do_html(base / HTML_IE))
    df, nao, faltam, avisos = combinar(t13, p22, ztm_rgi, dim)
    conf = conferir_anexo_iv(df, iv)

    if falhas:
        avisos.insert(0, f"{len(falhas)} linhas da tabela de 2013 não lidas (ver linhas_nao_lidas)")
    if any(conf["divergencias"].values()):
        avisos.append(f"o resultado difere do trecho do Anexo IV: {conf['divergencias']}")
    if len(faltam):
        avisos.append(f"{len(faltam)} municípios da dim_municipio sem índice no INCRA: "
                      + ", ".join(f"{r.nome_municipio} ({r.uf})" for r in faltam.itertuples()))

    outs = save_table(df, PROCESSED_DIR / "dimensions" / "dim_modulo_fiscal")
    (INTERIM_DIR / "modulo_fiscal").mkdir(parents=True, exist_ok=True)
    nao_path = INTERIM_DIR / "modulo_fiscal" / "modulo_fiscal_nao_correspondidos.csv"
    nao.to_csv(nao_path, sep=";", index=False, encoding="utf-8")

    fmp_mudou = int(p22["fmp"].ne(p22["fmp_antiga"]).sum())
    write_manifest("dim_modulo_fiscal", source=FONTE, reference_date=DATA_REFERENCIA,
                   source_files=[str(p) for p in brutos],
                   row_count=len(df), municipality_count=df["cod_municipio"].nunique(),
                   rejected_rows=len(nao) + len(falhas),
                   output_files=outs + [str(nao_path)], warnings=avisos,
                   extra={"fmp_alterada_em_2022": fmp_mudou,
                          "conferencia_anexo_iv": conf,
                          "linhas_nao_lidas": falhas[:20],
                          "nomes_diferentes": _nomes_diferentes(t13, dim)})
    print(f"[MÓDULO FISCAL] {len(df):,} municípios · FMP de 2022 em {fmp_mudou:,} · "
          f"Anexo IV: {conf['municipios']} conferidos, divergências {conf['divergencias']}")
    for a in avisos:
        print(f"  [AVISO] {a}")


if __name__ == "__main__":
    main()
