"""
process_pevs.py — PEVS por município, produto e ano (Etapa 1, §6.8).

Consome o consolidado PEVS_municipios_completo.csv (copiado para data/raw/ibge/pevs/
por download_pevs.py) e produz a tabela longa `pevs_municipio`, mantendo
silvicultura e extração vegetal IDENTIFICADAS separadamente e aplicando os grupos
editáveis de config/forestry_groups.csv.

O grupo casa pelo código interno do SIDRA (Cod_Categoria), não pelo rótulo, que vem
com a numeração do IBGE na frente e mudou em 2025. Só o nível "produto" recebe
grupo: os agregados do IBGE ("1.3 - Madeira em tora" = 1.3.1 + 1.3.2), a abertura da
silvicultura por espécie (só desde 2013) e a contagem de árvores do pinheiro
brasileiro ficam sem grupo. Assim, somar por grupo não repete produção, e o valor das
linhas com grupo fecha com o Total do IBGE.

NÃO reimplementa o process_pevs.py do dashboard (que gera pevs.json). Aqui o alvo
é a base analítica complementar (parquet/csv), não o JSON do front-end.

Saída:
  data/processed/municipality/pevs_municipio.parquet | .csv
  data/manifests/pevs_municipio.json

Estrutura: cod_municipio, ano, tipo_atividade, produto, variavel, quantidade,
valor_producao_mil_reais, unidade_quantidade, grupo, fonte_tabela_sidra.
Descarta a categoria "Total" (soma sem sentido físico). Ausência = null.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import (  # noqa: E402
    RAW_DIR, PROCESSED_DIR, CONFIG_DIR, cod_mun7, clean_num, save_table, write_manifest,
)

TIPO_LABEL = {"Silvicultura": "Silvicultura", "Extracao": "Extração vegetal",
              "AreaSilvicultura": "Área plantada (silvicultura)"}
TIPO_TABELA = {"Silvicultura": 291, "Extracao": 289, "AreaSilvicultura": 5930}
NIVEIS = {"produto", "agregado", "especie", "contagem"}  # só "produto" tem grupo


def _read_pevs() -> pd.DataFrame:
    p = RAW_DIR / "ibge" / "pevs" / "PEVS_municipios_completo.csv"
    if not p.exists():
        raise SystemExit("PEVS consolidado ausente. Rode download/download_pevs.py primeiro.")
    df = pd.read_csv(p, sep=";", encoding="utf-8-sig",
                     dtype={"Cod_Municipio": str, "Cod_Categoria": str})
    # Em 2025 o IBGE renumerou produtos (castanhas, erva-mate, carvão, lenha e
    # madeira por espécie): o rótulo muda, o código interno do SIDRA não. O produto
    # segue pelo código, com o rótulo mais recente — como no pevs.json do painel.
    recente = df.sort_values("Ano").groupby(["Tipo", "Cod_Categoria"])["Categoria"].last()
    df["Categoria"] = [re.sub(r"^(\d+(?:\.\d+)*)\s+(?!-)", r"\1 - ", str(recente.get((t, c), cat)).strip())
                       for t, c, cat in zip(df["Tipo"], df["Cod_Categoria"], df["Categoria"])]
    return df


def _grupos() -> dict:
    """(tipo_atividade, cod_categoria) -> grupo; None onde o grupo repetiria produção."""
    g = pd.read_csv(CONFIG_DIR / "forestry_groups.csv", sep=";", dtype=str,
                    comment="#", keep_default_na=False).apply(lambda s: s.str.strip())
    erros = []
    repetidos = g[g.duplicated(["tipo_atividade", "cod_categoria"], keep=False)]
    if len(repetidos):
        erros.append("código repetido: " + ", ".join(sorted(set(repetidos["cod_categoria"]))))
    if not g["nivel"].isin(NIVEIS).all():
        erros.append("nível fora de " + "/".join(sorted(NIVEIS)))
    trocados = g[(g["nivel"] == "produto") != (g["grupo"] != "")]
    if len(trocados):
        erros.append("só o nível produto tem grupo: " + ", ".join(trocados["produto"]))
    if erros:
        raise ValueError("config/forestry_groups.csv: " + "; ".join(erros))
    return {(r.tipo_atividade, r.cod_categoria): r.grupo or None for r in g.itertuples()}


def build() -> pd.DataFrame:
    return _montar()[0]


def _montar() -> tuple[pd.DataFrame, list[str]]:
    """Tabela longa + avisos dos códigos que não têm linha na config (ficam sem grupo)."""
    df = _read_pevs()
    df = df[df["Categoria"].astype(str).str.strip().str.lower() != "total"].copy()
    grupos = _grupos()

    rows, sem_config = [], {}
    for _, r in df.iterrows():
        tipo_raw = str(r.get("Tipo", ""))
        produto = str(r.get("Categoria", ""))
        chave = (tipo_raw, str(r.get("Cod_Categoria", "")).strip())
        if chave not in grupos:
            sem_config[chave] = produto
        grupo = grupos.get(chave)
        q = clean_num(r.get("q")) if "q" in df.columns else None
        v = clean_num(r.get("v")) if "v" in df.columns else None
        a = clean_num(r.get("a")) if "a" in df.columns else None
        rows.append({
            "cod_municipio": cod_mun7(r.get("Cod_Municipio")),
            "ano": int(r["Ano"]) if str(r.get("Ano", "")).isdigit() else None,
            "tipo_atividade": TIPO_LABEL.get(tipo_raw, tipo_raw),
            "produto": produto,
            "quantidade": q if tipo_raw != "AreaSilvicultura" else None,
            "area_ha": a if tipo_raw == "AreaSilvicultura" else None,
            "valor_producao_mil_reais": v,
            "unidade_quantidade": r.get("Unidade") or None,
            "grupo": grupo,
            "fonte_tabela_sidra": TIPO_TABELA.get(tipo_raw),
        })
    avisos = [f"{t} {c} ({p}) sem linha em config/forestry_groups.csv: fica sem grupo"
              for (t, c), p in sorted(sem_config.items())]
    return pd.DataFrame(rows), avisos


def main():
    df, avisos = _montar()
    outs = save_table(df, PROCESSED_DIR / "municipality" / "pevs_municipio")
    preenchimento = {t: {"linhas": int(n), "com_grupo": int(k)} for t, n, k in
                     df.groupby("tipo_atividade")["grupo"].agg(["size", "count"]).itertuples()}
    write_manifest("pevs_municipio", source="IBGE — PEVS (291/289/5930)",
                   reference_date=None, source_files=[str(RAW_DIR / 'ibge' / 'pevs' / 'PEVS_municipios_completo.csv')],
                   row_count=len(df), municipality_count=df["cod_municipio"].nunique(),
                   warnings=avisos, output_files=outs,
                   extra={"linhas_com_grupo": preenchimento})
    print(f"[PEVS] {len(df):,} linhas · municípios={df['cod_municipio'].nunique():,} · "
          f"anos={df['ano'].min()}–{df['ano'].max()}")
    for t, p in preenchimento.items():
        print(f"  {t}: {p['com_grupo']:,} de {p['linhas']:,} linhas com grupo")
    for aviso in avisos:
        print(f"  [AVISO] {aviso}")


if __name__ == "__main__":
    main()
