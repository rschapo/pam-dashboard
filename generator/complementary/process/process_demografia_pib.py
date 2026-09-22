"""
process_demografia_pib.py — Constrói mun_demografia_pib / uf_demografia_pib a
partir dos JSONs brutos gravados por download_demografia_pib.py.

Mesma lógica de campos de Base_Municipios_Brasil/scripts/coletar_base.py::
coletar_demografia_pib (mapa de variável SIDRA -> coluna, cálculo de
pct_agro_no_pib), agora lendo do arquivo já baixado em vez da API ao vivo —
permite rodar em ambiente sem rede (Cowork/CI) depois do download na máquina
do usuário.

Saídas:
  data/processed/municipality/demografia_pib.parquet | .csv
  data/processed/state/demografia_pib.parquet | .csv
  data/manifests/demografia_pib.json

Uso:
  python process_demografia_pib.py [--ano-pib 2023] [--ano-pop 2024]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import RAW_DIR, PROCESSED_DIR, cod_mun7, clean_num, save_table, write_manifest  # noqa: E402

CAMPO_POR_VARIAVEL = {
    "Produto Interno Bruto a preços correntes": "pib_total",
    "Valor adicionado bruto a preços correntes da agropecuária": "vab_agropecuaria",
    "Valor adicionado bruto a preços correntes da indústria": "vab_industria",
    "Valor adicionado bruto a preços correntes dos serviços": "vab_servicos",
    "Impostos, líquidos de subsídios, sobre produtos a preços correntes": "impostos_liquidos",
}
# PIB per capita não existe como variável na tabela 5938 — calculado abaixo
# a partir de pib_total (mil R$) / população (nº de pessoas).
VAB_COLS = ["vab_agropecuaria", "vab_industria", "vab_servicos"]


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
    soma_vab = df[VAB_COLS].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
    agro = pd.to_numeric(df["vab_agropecuaria"], errors="coerce")
    df["pct_agro_no_pib"] = (agro / soma_vab.replace(0, float("nan"))).round(4)
    # PIB per capita (R$): não existe como variável na 5938 — calculado aqui.
    # pib_total vem em Mil Reais (unidade da tabela) -> x1000 para reais correntes.
    if "populacao" in df:
        pib_total_reais = pd.to_numeric(df["pib_total"], errors="coerce") * 1000
        pop_num = pd.to_numeric(df["populacao"], errors="coerce")
        df["pib_per_capita"] = (pib_total_reais / pop_num.replace(0, float("nan"))).round(2)
    else:
        df["pib_per_capita"] = None
    df["ano_ref"] = ano_pib          # população + PIB total
    df["ano_ref_vab"] = ano_vab      # VAB setorial + pct_agro_no_pib (pode ser < ano_ref)
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
        print(f"  [AVISO] VAB setorial/pct_agro_no_pib referem-se a {sorted(anos_vab)}, "
              f"não a {args.ano_pib} — PIB total e população estão em {args.ano_pib}/{args.ano_pop}. "
              "Ver coluna ano_ref_vab.")

    write_manifest(
        "demografia_pib",
        source="IBGE/SIDRA (tabela 5938 PIB total + VAB setorial, tabela 6579 população)",
        reference_date=f"{args.ano_pib}-01-01",
        source_files=[str(p) for p in (RAW_DIR / "ibge").glob("sidra_p*_*.json")]
                     + [str(p) for p in (RAW_DIR / "ibge").glob("sidra_vabsetorial_*.json")],
        output_files=outs_all,
        extra={"ano_pib": args.ano_pib, "ano_pop": args.ano_pop,
               "anos_vab_efetivos": sorted(anos_vab)},
    )
    print("Concluído.")


if __name__ == "__main__":
    main()
