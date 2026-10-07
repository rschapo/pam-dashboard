"""
process_demografia_pib.py — Constrói mun_demografia_pib / uf_demografia_pib a
partir dos JSONs brutos gravados por download_demografia_pib.py.

Mesma lógica de campos de Base_Municipios_Brasil/scripts/coletar_base.py::
coletar_demografia_pib (mapa de variável SIDRA -> coluna), agora lendo do
arquivo já baixado em vez da API ao vivo — permite rodar em ambiente sem rede
(Cowork/CI) depois do download na máquina do usuário.

pct_agro_no_vab é a participação da agropecuária no VAB total, em %, os dois do
ano do VAB setorial (ano_ref_vab). Não se divide pelo PIB total, que é de outro
ano (ano_ref), nem pela soma agro + indústria + serviços, que deixa de fora a
administração pública.

pib_per_capita divide o PIB pela população que o IBGE usa no per capita oficial do
mesmo ano (populacao_pib). Ela vem da base do PIB dos Municípios, como PIB ÷ per
capita: para 2023, sem estimativa publicada, é a relação enviada ao TCU em 2023, o
Censo 2022 com os limites municipais revistos até abril de 2023 (nota 3 da base). A
tabela 4709 do Censo difere dela em 134 municípios, quase todos de PE, AL e RS.
populacao segue sendo a estimativa mais recente (--ano-pop), como indicador.

Saídas:
  data/processed/municipality/demografia_pib.parquet | .csv
  data/processed/state/demografia_pib.parquet | .csv
  data/manifests/demografia_pib.json

Uso:
  python process_demografia_pib.py [--ano-pib 2023] [--ano-pop 2024]
"""
from __future__ import annotations

import argparse
import functools
import io
import json
import re
import zipfile
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import RAW_DIR, PROCESSED_DIR, cod_mun7, clean_num, save_table, write_manifest  # noqa: E402

CAMPO_POR_VARIAVEL = {
    "Produto Interno Bruto a preços correntes": "pib_total",
    "Valor adicionado bruto a preços correntes total": "vab_total",
    "Valor adicionado bruto a preços correntes da agropecuária": "vab_agropecuaria",
    "Valor adicionado bruto a preços correntes da indústria": "vab_industria",
    # "…dos serviços, exclusive administração, defesa, educação e saúde públicas…"
    "Valor adicionado bruto a preços correntes dos serviços": "vab_servicos",
    "Valor adicionado bruto a preços correntes da administração": "vab_adm_publica",
    "Impostos, líquidos de subsídios, sobre produtos a preços correntes": "impostos_liquidos",
}
# PIB per capita não existe como variável na tabela 5938 — calculado abaixo
# a partir de pib_total (mil R$) / população (nº de pessoas).
VAB_COLS = ["vab_agropecuaria", "vab_industria", "vab_servicos", "vab_adm_publica", "vab_total"]


def _load(path: Path) -> list:
    if not path.exists():
        raise SystemExit(f"Não encontrado: {path}\nRode antes: python download_demografia_pib.py")
    return json.loads(path.read_text(encoding="utf-8"))


def _achar_vab_json(escopo: str) -> tuple[Path, int]:
    """Descobre o arquivo sidra_vabsetorial_<escopo>_<ano>.json mais recente
    (o ano efetivo pode ser < ano_pib — ver nota no download_demografia_pib.py)."""
    candidatos = sorted((RAW_DIR / "ibge").glob(f"sidra_vabsetorial_{escopo}_*.json"))
    if not candidatos:
        raise SystemExit(f"Não encontrado sidra_vabsetorial_{escopo}_*.json — rode download_demografia_pib.py")
    p = candidatos[-1]  # maior ano (ordenação lexicográfica funciona p/ 4 dígitos)
    ano = int(p.stem.rsplit("_", 1)[-1])
    return p, ano


def _campo(nome_variavel: str) -> str | None:
    # prefixo mais específico primeiro para não confundir os 3 "Valor adicionado
    # bruto a preços correntes d..." entre si (agropecuária/indústria/serviços
    # compartilham os primeiros ~30 caracteres).
    for prefixo, campo in sorted(CAMPO_POR_VARIAVEL.items(), key=lambda kv: -len(kv[0])):
        if nome_variavel.startswith(prefixo):
            return campo
    return None


def _norm_cod(raw: str, chave: str) -> str | None:
    if chave == "cod_ibge":
        return cod_mun7(raw)
    s = re.sub(r"\D", "", str(raw))
    return s or None


def _wide_de(js: list, chave: str) -> pd.DataFrame:
    df = pd.DataFrame(js[1:]) if len(js) > 1 else pd.DataFrame()
    if df.empty:
        return df
    varcol = "D2N" if "D2N" in df.columns else "D3N"
    df[chave] = df["D1C"].map(lambda v: _norm_cod(v, chave))
    df["valor"] = df["V"].map(clean_num)
    df["campo"] = df[varcol].map(_campo)
    df = df.dropna(subset=["campo", chave])
    return df.pivot_table(index=chave, columns="campo", values="valor", aggfunc="first").reset_index()


@functools.lru_cache(maxsize=None)
def _populacao_do_pib(ano_pib: int) -> pd.DataFrame:
    """População do per capita oficial por município: PIB ÷ PIB per capita da base do
    PIB dos Municípios (download_demografia_pib.baixar_base_pib)."""
    p = RAW_DIR / "ibge" / f"pib_municipios_base_2010_{ano_pib}.zip"
    if not p.exists():
        raise SystemExit(f"Não encontrado: {p}\nRode antes: python download_demografia_pib.py")
    with zipfile.ZipFile(p) as z:
        nome = next(n for n in z.namelist() if n.lower().endswith(".xlsx"))
        b = pd.read_excel(io.BytesIO(z.read(nome)), sheet_name=0)
    b.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in b.columns]
    b = b[b["Ano"] == ano_pib]
    pib = next(c for c in b.columns if c.startswith("Produto Interno Bruto, "))
    pc = next(c for c in b.columns if "per capita" in c)
    return pd.DataFrame({"cod_ibge": b["Código do Município"].map(cod_mun7),
                         "populacao_pib": (b[pib] * 1000 / b[pc]).round()})


def build(nivel: str, ano_pib: int, ano_pop: int) -> pd.DataFrame:
    escopo = "municipios" if nivel == "6" else "uf"
    chave = "cod_ibge" if nivel == "6" else "cod_uf"

    pop_js = _load(RAW_DIR / "ibge" / f"sidra_populacao_{escopo}_{ano_pop}.json")
    pibtotal_js = _load(RAW_DIR / "ibge" / f"sidra_pibtotal_{escopo}_{ano_pib}.json")
    vab_path, ano_vab = _achar_vab_json(escopo)
    vab_js = json.loads(vab_path.read_text(encoding="utf-8"))

    pop = pd.DataFrame(pop_js[1:]) if len(pop_js) > 1 else pd.DataFrame()
    if not pop.empty:
        pop[chave] = pop["D1C"].map(lambda v: _norm_cod(v, chave))
        pop["populacao"] = pd.to_numeric(pop["V"], errors="coerce")
        pop = pop[[chave, "populacao"]]

    pop_pib = _populacao_do_pib(ano_pib)
    if chave == "cod_uf":
        pop_pib = (pop_pib.assign(cod_uf=pop_pib["cod_ibge"].str[:2])
                   .groupby("cod_uf", as_index=False)["populacao_pib"].sum())
    pop = pop.merge(pop_pib, on=chave, how="outer") if not pop.empty else pop_pib

    pibtotal_wide = _wide_de(pibtotal_js, chave)
    vab_wide = _wide_de(vab_js, chave)
    if pibtotal_wide.empty and vab_wide.empty:
        return pd.DataFrame()

    df = pop
    for parte in (pibtotal_wide, vab_wide):
        if not parte.empty:
            df = df.merge(parte, on=chave, how="outer") if not df.empty else parte

    for c in VAB_COLS + ["pib_total"]:
        if c not in df:
            df[c] = None
    agro = pd.to_numeric(df["vab_agropecuaria"], errors="coerce")
    vab_total = pd.to_numeric(df["vab_total"], errors="coerce")
    df["pct_agro_no_vab"] = (100 * agro / vab_total.replace(0, float("nan"))).round(2)
    # PIB per capita (R$): não existe como variável na 5938 — calculado aqui, com a
    # população do per capita oficial. pib_total vem em Mil Reais -> x1000.
    pib_total_reais = pd.to_numeric(df["pib_total"], errors="coerce") * 1000
    pop_num = pd.to_numeric(df["populacao_pib"], errors="coerce")
    df["pib_per_capita"] = (pib_total_reais / pop_num.replace(0, float("nan"))).round(2)
    df["ref_populacao_pib"] = (f"Censo 2022, como no per capita oficial do IBGE" if ano_pib >= 2022
                               else f"estimativa de {ano_pib}, como no per capita oficial do IBGE")
    df["ano_ref"] = ano_pib          # população + PIB total
    df["ano_ref_vab"] = ano_vab      # VAB setorial + pct_agro_no_vab (pode ser < ano_ref)
    df["fonte"] = "IBGE/SIDRA (tabelas 5938 e 6579)"
    df = df.dropna(subset=[chave]).sort_values(chave).reset_index(drop=True)
    return df, ano_vab


def main():
    ap = argparse.ArgumentParser(description="Constrói demografia_pib (municípios + UF)")
    ap.add_argument("--ano-pib", type=int, default=2023)
    ap.add_argument("--ano-pop", type=int, default=2024)
    args = ap.parse_args()

    outs_all = []
    anos_vab = set()
    for nivel, pasta, nome in (("6", PROCESSED_DIR / "municipality", "demografia_pib"),
                                ("3", PROCESSED_DIR / "state", "demografia_pib")):
        resultado = build(nivel, args.ano_pib, args.ano_pop)
        if resultado is None or resultado[0].empty:
            print(f"  [AVISO] nível {nivel}: nenhum dado (rode download_demografia_pib.py antes)")
            continue
        df, ano_vab = resultado
        anos_vab.add(ano_vab)
        outs = save_table(df, pasta / nome)
        outs_all += outs
        print(f"  {nome} ({'município' if nivel=='6' else 'UF'}): {len(df):,} linhas -> {[Path(o).name for o in outs]}")

    if anos_vab and anos_vab != {args.ano_pib}:
        print(f"  [AVISO] VAB setorial/pct_agro_no_vab referem-se a {sorted(anos_vab)}, "
              f"não a {args.ano_pib} — PIB total e população estão em {args.ano_pib}/{args.ano_pop}. "
              "Ver coluna ano_ref_vab.")

    write_manifest(
        "demografia_pib",
        source="IBGE/SIDRA (tabela 5938 PIB total + VAB setorial, 6579 população estimada) "
               "e base do PIB dos Municípios (população do per capita)",
        reference_date=f"{args.ano_pib}-01-01",
        source_files=[str(p) for p in (RAW_DIR / "ibge").glob("sidra_p*_*.json")]
                     + [str(p) for p in (RAW_DIR / "ibge").glob("sidra_vabsetorial_*.json")],
        output_files=outs_all,
        extra={"ano_pib": args.ano_pib, "ano_pop": args.ano_pop,
               "populacao_do_per_capita": "base do PIB dos Municípios (PIB ÷ per capita oficial)",
               "anos_vab_efetivos": sorted(anos_vab)},
    )
    print("Concluído.")


if __name__ == "__main__":
    main()
