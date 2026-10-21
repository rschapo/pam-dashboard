"""
process_produtores.py — produtores rurais pela base CNPJ da Receita: CONTAGEM ANÔNIMA
por município, atividade e tipo (opção A, decisão do usuário de 21/10/2026). O painel
público é do Brasil inteiro, sem senha: nada que identifique pessoa chega a public/.

Universo: estabelecimentos ATIVOS (situação 02) com CNAE principal das divisões 01
(agricultura, pecuária e serviços relacionados) e 02 (produção florestal), 27 UFs,
pessoa física (produtor rural, natureza 4120), jurídica (2xxx) e outras naturezas.

  - atividade pelo CNAE principal declarado: config/cnae_atividade_produtores.csv, uma
    linha por subclasse; CNAE que não estiver na tabela ABORTA a rodada;
  - lista de exclusão (opt-out) <cache>/exclusoes_lgpd.csv, aplicada ANTES de contar e
    de gravar a base local: quem pediu para sair some de tudo;
  - "abertos nos últimos 24 meses" pela data de início de atividade, contra a data mais
    recente de abertura na própria base do período (o dia da extração da Receita);
  - sem supressão de célula pequena por padrão (a contagem vem de cadastro público e
    não revela atributo novo de ninguém); `--suprimir-abaixo N` troca 1..N-1 por null.

Saídas:
  <cache fora do OneDrive>/produtores_base_<período>.parquet  (com identificador: só local)
  data/processed/municipality/produtores_municipio.parquet + .csv  (sem identificador)
  public/data/produtores_mun.json  (só códigos IBGE e números)

Uso: python process/process_produtores.py [--suprimir-abaixo N]
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import PROCESSED_DIR, now_iso, save_table, write_manifest, write_public_json  # noqa: E402
import receita_common as rc  # noqa: E402

PUBLIC_DATA = Path(__file__).resolve().parents[3] / "public" / "data"
CNAE_CSV = rc.CONFIG_DIR / "cnae_atividade_produtores.csv"

ATIVIDADES = {
    "cana": "Cana-de-açúcar",
    "citros": "Citros",
    "cafe": "Café",
    "graos": "Grãos, oleaginosas e fibras",
    "hf": "Hortaliças e frutas (H&F)",
    "bovinos": "Bovinos (corte e leite)",
    "aves_suinos": "Aves, suínos e outros animais",
    "florestal": "Florestal (plantada e nativa)",
    "servicos": "Serviços agropecuários (inclui serviço com máquinas)",
    "outros": "Outras atividades agropecuárias",
}
CABECALHO_EXCLUSOES = ["cnpj", "data", "canal", "responsavel"]

CAUTELAS = [
    "Conta CADASTROS ativos na Receita (CNPJ), não produtores nem estabelecimentos agropecuários do Censo: "
    "muitos produtores operam só com CPF e inscrição estadual e não aparecem aqui.",
    "Um produtor pode ter vários cadastros (um por imóvel ou inscrição estadual), e um cadastro conta uma vez.",
    "A atividade é o CNAE principal declarado à Receita; a atividade real pode ser outra ou mais de uma.",
    "Retrato do período da base da Receita, sem série histórica.",
    "Só contagens por município: nome, CNPJ, endereço e contato não saem da base local.",
]


# ──────────────────────────────────────────────────────────────────────────────
# Funções puras (testadas sem o banco)
# ──────────────────────────────────────────────────────────────────────────────
def mapa_cnae(path: Path = CNAE_CSV) -> dict[str, str]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return {r["cnae"].strip(): r["atividade"].strip() for r in csv.DictReader(fh, delimiter=";")}


def classificar_atividade(cnaes: pd.Series, mapa: dict[str, str]) -> pd.Series:
    """CNAE → atividade pela tabela. CNAE fora dela não vira "outros" em silêncio:
    a rodada para e pede a revisão da tabela."""
    fora = sorted(set(cnaes.dropna().astype(str)) - set(mapa))
    if fora:
        raise SystemExit(f"CNAE sem atividade em {CNAE_CSV.name}: {fora}")
    return cnaes.astype(str).map(mapa)


def carregar_exclusoes(path: Path) -> tuple[set[str], set[str]]:
    """(CNPJ completos, CNPJ raiz) da lista de exclusão. Cria o arquivo só com o
    cabeçalho se ele não existir. Raiz (8 dígitos) exclui todos os estabelecimentos."""
    if not path.exists():
        with open(path, "w", encoding="utf-8", newline="") as fh:
            csv.writer(fh, delimiter=";").writerow(CABECALHO_EXCLUSOES)
        return set(), set()
    with open(path, encoding="utf-8-sig", newline="") as fh:
        ids = ["".join(ch for ch in (r.get("cnpj") or "") if ch.isdigit())
               for r in csv.DictReader(fh, delimiter=";")]
    return {i for i in ids if len(i) == 14}, {i for i in ids if len(i) == 8}


def aplicar_exclusoes(df: pd.DataFrame, cnpj14: set[str], raiz8: set[str]) -> tuple[pd.DataFrame, int]:
    fora = df["cnpj"].isin(cnpj14) | df["cnpj"].str[:8].isin(raiz8)
    return df[~fora].copy(), int(fora.sum())


def agregar(df: pd.DataFrame, corte_24m: str) -> pd.DataFrame:
    """Município × atividade × tipo: cadastros ativos e abertos desde o corte (AAAAMMDD)."""
    d = df[df["cod_municipio"].notna()].copy()
    d["novo"] = d["data_inicio"].astype(str) >= corte_24m
    return (d.groupby(["cod_municipio", "atividade", "tipo"])
              .agg(ativos=("cnpj", "size"), novos_24m=("novo", "sum"))
              .reset_index())


def suprimir(v: int, abaixo: int):
    return None if abaixo and 0 < v < abaixo else int(v)


def json_mun(ag: pd.DataFrame, abaixo: int = 0) -> dict:
    """{cod7: {"atividade|tipo": [ativos, novos_24m]}} só com as combinações > 0."""
    mun: dict[str, dict] = {}
    for r in ag.itertuples(index=False):
        if r.ativos <= 0:
            continue
        mun.setdefault(str(r.cod_municipio), {})[f"{r.atividade}|{r.tipo}"] = [
            suprimir(r.ativos, abaixo), suprimir(r.novos_24m, abaixo)]
    return mun


def comparacao_censo(ag: pd.DataFrame, censo: pd.DataFrame) -> dict:
    """Cadastros ativos por UF contra os estabelecimentos do Censo Agro 2017. Só a razão:
    são universos diferentes, e nada aqui é "corrigido"."""
    a = ag.assign(uf=ag["cod_municipio"].astype(str).str[:2]).groupby("uf")["ativos"].sum()
    c = censo.assign(uf=censo["cod_municipio"].astype(str).str[:2]).groupby("uf")["numero_estabelecimentos"].sum()
    from common import IBGE2UF
    out = {}
    for cod in sorted(set(a.index) | set(c.index)):
        uf = IBGE2UF.get(cod)
        if not uf:
            continue
        n, e = int(a.get(cod, 0)), int(c.get(cod, 0) or 0)
        out[uf] = {"cadastros": n, "censo2017": e, "razao": round(n / e, 3) if e else None}
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Extração e saídas
# ──────────────────────────────────────────────────────────────────────────────
def extrair(con) -> pd.DataFrame:
    return con.execute("""
        WITH e AS (
          SELECT cnpj_basico, cnpj_ordem, cnpj_dv, cnae_principal, data_inicio, uf, municipio
          FROM estabelecimentos
          WHERE situacao_cadastral = '02' AND substr(cnae_principal, 1, 2) IN ('01', '02'))
        SELECT e.cnpj_basico || e.cnpj_ordem || e.cnpj_dv AS cnpj, e.cnae_principal, e.data_inicio,
               e.uf, e.municipio AS mun_rfb, m.natureza_juridica, m.razao_social
        FROM e LEFT JOIN empresas m ON m.cnpj_basico = e.cnpj_basico
    """).df()


def data_referencia(con) -> str:
    """Dia da extração da Receita: a abertura mais recente da base, sem datas futuras."""
    hoje = pd.Timestamp.today().strftime("%Y%m%d")
    return con.execute("SELECT max(data_inicio) FROM estabelecimentos WHERE data_inicio <= ?",
                       [hoje]).fetchone()[0]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--suprimir-abaixo", type=int, default=0,
                    help="troca contagens de 1 a N-1 por null no JSON público (padrão 0: não suprime)")
    args = ap.parse_args()
    t0 = time.time()
    per = rc.periodo_atual()
    cache = rc.pf_cache_dir()
    con = rc.conectar(per)
    d = extrair(con)
    ref = data_referencia(con)
    muns = dict(con.execute("SELECT codigo, descricao FROM municipios").fetchall())
    con.close()
    t_ext = time.time() - t0
    print(f"base CNPJ {per}: {len(d):,} estabelecimentos agropecuários ativos ({t_ext:.0f}s); referência {ref}")

    cnpj14, raiz8 = carregar_exclusoes(cache / "exclusoes_lgpd.csv")
    d, n_excl = aplicar_exclusoes(d, cnpj14, raiz8)
    print(f"  exclusões LGPD aplicadas: {n_excl} (lista com {len(cnpj14)} CNPJ e {len(raiz8)} raízes)")

    d["tipo"] = d["natureza_juridica"].map(rc.tipo_natureza)
    d["atividade"] = classificar_atividade(d["cnae_principal"], mapa_cnae())
    d["municipio_rfb"] = d["mun_rfb"].map(muns)
    pares = set(zip(d["municipio_rfb"], d["uf"]))
    mapa, sem = rc.casar_municipios(pares)
    d["cod_municipio"] = [mapa.get((m, u)) for m, u in zip(d["municipio_rfb"], d["uf"])]
    sem_cod = int(d["cod_municipio"].isna().sum())

    ref_ts = pd.Timestamp(ref)
    corte = (ref_ts - pd.DateOffset(months=24)).strftime("%Y%m%d")

    base_cols = ["cnpj", "natureza_juridica", "tipo", "cnae_principal", "atividade", "uf",
                 "cod_municipio", "data_inicio", "razao_social"]
    d[base_cols].to_parquet(cache / f"produtores_base_{per}.parquet", index=False)

    ag = agregar(d, corte)
    ag["periodo_rfb"] = per
    outs = save_table(ag, PROCESSED_DIR / "municipality" / "produtores_municipio")
    censo = pd.read_parquet(PROCESSED_DIR / "municipality" / "censo_agro_municipio_summary.parquet",
                            columns=["cod_municipio", "numero_estabelecimentos"])
    comp = comparacao_censo(ag, censo)

    obj = {
        "fonte": "Receita Federal, Dados Abertos CNPJ: estabelecimentos ativos com CNAE principal das divisões 01 e 02",
        "periodo_rfb": per,
        "data_ref": f"{ref_ts:%Y-%m-%d}",
        "corte_24m": f"{pd.Timestamp(corte):%Y-%m-%d}",
        "gerado_em": now_iso(),
        "atividades": ATIVIDADES,
        "tipos": rc.TIPOS,
        "cautelas": CAUTELAS,
        "suprimido_abaixo": args.suprimir_abaixo,
        "comparacao_censo_uf": comp,
        "mun": json_mun(ag, args.suprimir_abaixo),
    }
    pub = write_public_json(PUBLIC_DATA / "produtores_mun.json", obj)
    write_manifest("produtores_rurais", source=f"Receita Federal CNPJ {per}", reference_date=obj["data_ref"],
                   row_count=len(d), municipality_count=len(obj["mun"]), rejected_rows=sem_cod,
                   warnings=[f"município da Receita sem par IBGE: {n} ({u})" for n, u in sem],
                   output_files=outs + [str(pub)],
                   extra={"exclusoes_aplicadas": n_excl, "suprimido_abaixo": args.suprimir_abaixo,
                          "por_tipo": {k: int(v) for k, v in d.groupby("tipo").size().items()}})

    print(f"  agregado: {int(ag['ativos'].sum()):,} cadastros em {len(obj['mun']):,} municípios · "
          f"{pub.stat().st_size / 1_048_576:.2f} MB · sem município IBGE: {sem_cod} · {time.time() - t0:.0f}s")
    print(d.groupby(["atividade", "tipo"]).size().unstack(fill_value=0).to_string())
    print(f"  municípios da Receita sem par: {sem}")
    for uf, v in comp.items():
        print(f"  {uf}: {v}")


if __name__ == "__main__":
    main()
