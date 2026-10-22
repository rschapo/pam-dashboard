"""
process_contas_chave.py — contas-chave da agroindústria pela base CNPJ da Receita, nas
27 UFs, com as usinas validadas pela ANP. Só pessoa jurídica empresarial, e o painel
público recebe só AGREGADOS por município e setor.

A Receita não diz "usina": diz CNAE. O CNAE sozinho conta escritório e comercializadora
como usina e deixa de fora a planta registrada com CNAE agrícola. Por isso:
  - o recorte usa o CNAE PRINCIPAL do estabelecimento ATIVO (situação 02);
  - a usina é cruzada, pelo CNPJ completo, com a capacidade autorizada de etanol da
    ANP: a planta autorizada que a Receita registra com outro CNAE entra como usina, e o
    estabelecimento com CNAE de usina sem autorização fica "confirmar" (pode ser só de
    açúcar, escritório, refinaria, ou estar em recuperação judicial) desde que a empresa
    tenha capital social ≥ R$ 1 mi: abaixo disso são, quase sempre, pequenos fabricantes de
    melado, açúcar mascavo e álcool artesanal (no RS, 98 dos 109 "confirmar" em 10/2026,
    capital mediano de R$ 10 mil), e ficam fora;
  - a fazenda (0113-0/00) de um CNPJ raiz que tem usina é "unidade agrícola de grupo
    sucroenergético": mostra onde o grupo opera, não é uma usina a mais;
  - sucos e eucalipto só com capital social ≥ R$ 1 mi (o porte "05 — Demais" da Receita
    é tudo o que não é ME/EPP e não separa o grande);
  - SÓ natureza jurídica 2xxx. O produtor rural pessoa física (4120) aparece em massa
    nesses CNAEs, e a razão social dele é o nome da pessoa: dado pessoal, vai só para a
    contagem anônima de produtores (process_produtores.py).
Sem sócios (QSA).

Saídas:
  <cache fora do OneDrive>/contas_chave_detalhe_<período>.parquet   (com razão social e CNPJ)
  data/processed/municipality/contas_chave_municipio.parquet + .csv  (município × setor, sem nomes)
  data/manifests/contas_chave.json                                   (validação ANP × Receita, contagens)
  public/data/contas_chave.json                                      (agregado do painel)

Uso: python process/process_contas_chave.py
"""
from __future__ import annotations

import io
import re
import sys
import time
import unicodedata
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import (MANIFEST_DIR, PROCESSED_DIR, RAW_DIR, UF_NAMES, now_iso,  # noqa: E402
                    save_table, write_manifest, write_public_json)
import receita_common as rc  # noqa: E402

PUBLIC_DATA = Path(__file__).resolve().parents[3] / "public" / "data"

SETORES = {   # chave do painel: (rótulo, cor do círculo)
    "usina_anp":      ("Usina de açúcar e etanol com autorização da ANP", "#3E7D1E"),
    "usina_conf":     ("CNAE de usina sem autorização de etanol da ANP, capital ≥ R$ 1 mi (confirmar)", "#A5C882"),
    "usina_agricola": ("Unidade agrícola de grupo sucroenergético", "#9CCB6A"),
    "sucos":          ("Indústria de suco (capital ≥ R$ 1 mi)", "#F28C28"),
    "pos_colheita":   ("Pós-colheita / packing", "#C2185B"),
    "cafe":           ("Café: beneficiamento e comércio atacadista", "#8B5A2B"),
    "florestal":      ("Florestal: celulose e eucalipto (capital ≥ R$ 1 mi)", "#1B5E20"),
    "cooperativa":    ("Cooperativa agropecuária", "#1565C0"),
}
CNAE_USINA = {"1071600", "1072401", "1931400"}
CNAE_CANDIDATOS = sorted(CNAE_USINA | {"0113000", "1033301", "0163600", "1081301", "4621400",
                                       "1710900", "0210101"})
CAPITAL_GRANDE = 1_000_000

CAUTELAS = [
    "A Receita não classifica 'usina': o recorte usa o CNAE principal do estabelecimento ativo. "
    "Usina sem autorização de etanol na ANP fica marcada para confirmar (pode ser só de açúcar, "
    "escritório, refinaria ou estar em recuperação judicial), e só quando a empresa tem capital social "
    "≥ R$ 1 mi: as menores são, quase sempre, fabricantes de melado, açúcar mascavo e álcool artesanal.",
    "Unidade agrícola de grupo = fazenda (CNAE 0113-0/00) de um CNPJ raiz que tem usina: mostra onde o "
    "grupo opera, não é uma usina a mais.",
    "Sucos e eucalipto: só empresas com capital social ≥ R$ 1 mi; as pequenas são muitas e não são contas-chave.",
    "Só pessoa jurídica empresarial (natureza 2xxx). O produtor rural pessoa física fica de fora por ser "
    "dado pessoal; ele aparece só na contagem anônima de produtores.",
    "Conta ESTABELECIMENTOS (matriz e filiais), não empresas nem tamanho. Posição = ponto do município, "
    "não endereço.",
]


# ──────────────────────────────────────────────────────────────────────────────
# ANP
# ──────────────────────────────────────────────────────────────────────────────
def _letras(t) -> str:
    """Nome de UF da ANP comparado só pelas letras ASCII, sem caixa e sem acento:
    "São Paulo" e "SAO PAULO" dão "saopaulo"."""
    s = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z]", "", s.lower())


UF_POR_NOME = {_letras(n): uf for uf, n in UF_NAMES.items()}


def ler_anp(zip_path: Path) -> tuple[pd.DataFrame, str]:
    """Capacidade autorizada do ÚLTIMO mês do arquivo 2021-2026. O separador e a
    codificação mudam entre versões do arquivo: separador detectado, UTF-8 com BOM
    quando for o caso e latin-1 se não, colunas pela POSIÇÃO."""
    z = zipfile.ZipFile(zip_path)
    nome = next(n for n in z.namelist() if "Capacidade" in n and "2021" in n)
    bruto = z.read(nome)
    try:
        texto = bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = bruto.decode("latin-1")
    anp = pd.read_csv(io.StringIO(texto), sep=None, engine="python", dtype=str)
    anp = anp.iloc[:, :8]
    anp.columns = ["mes", "razao", "cnpj", "regiao", "estado", "municipio", "cap_anidro", "cap_hidratado"]
    anp["ord"] = pd.to_datetime("01/" + anp["mes"].str.strip(), format="%d/%m/%Y", errors="coerce")
    mes = anp["ord"].max()
    anp = anp[anp["ord"] == mes].copy()
    anp["cnpj"] = anp["cnpj"].str.replace(r"\D", "", regex=True).str.zfill(14)
    anp["uf"] = anp["estado"].map(lambda s: UF_POR_NOME.get(_letras(s)))
    for c in ("cap_anidro", "cap_hidratado"):
        anp[c] = pd.to_numeric(anp[c].str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
                               errors="coerce").fillna(0)
    anp["cap_total_m3d"] = anp["cap_anidro"] + anp["cap_hidratado"]
    return anp.drop(columns="ord").reset_index(drop=True), f"{mes:%m/%Y}"


# ──────────────────────────────────────────────────────────────────────────────
# Classificação (pura: testada sem o banco)
# ──────────────────────────────────────────────────────────────────────────────
def classificar(base: pd.DataFrame, anp_cnpjs: set[str]) -> tuple[pd.DataFrame, dict]:
    """Recebe estabelecimentos ativos candidatos (cnpj, cnpj_basico, cnae_principal,
    natureza_juridica, capital_social em texto) e devolve só os classificados, com
    `setor` (usina, usina_agricola, sucos, pos_colheita, cafe, florestal, cooperativa),
    `anp` e `confirmar`, mais as contagens de exclusão."""
    b = base.copy()
    nat = b["natureza_juridica"].astype(str)
    empresarial = nat.str.startswith("2")
    excl = {"excluidos_produtor_rural_pf": int((nat == "4120").sum()),
            "excluidos_outras_naturezas": int((~empresarial & (nat != "4120")).sum())}
    b = b[empresarial].copy()
    b["capital"] = pd.to_numeric(b["capital_social"].map(rc.capital_reais), errors="coerce")
    grande = b["capital"] >= CAPITAL_GRANDE
    b["anp"] = b["cnpj"].isin(anp_cnpjs)
    cnae = b["cnae_principal"].astype(str)
    s = pd.Series(pd.NA, index=b.index, dtype="object")
    # CNAE de usina sem autorização da ANP só conta com capital ≥ R$ 1 mi (ver o cabeçalho)
    pequena = cnae.isin(CNAE_USINA) & ~b["anp"] & ~grande
    excl["excluidos_usina_sem_anp_capital_menor_1mi"] = int(pequena.sum())
    s[(cnae.isin(CNAE_USINA) & ~pequena) | b["anp"]] = "usina"
    raizes_usina = set(b.loc[s == "usina", "cnpj_basico"])
    s[s.isna() & (cnae == "0113000") & b["cnpj_basico"].isin(raizes_usina)] = "usina_agricola"
    s[s.isna() & (cnae == "1033301") & grande] = "sucos"
    s[s.isna() & (cnae == "0163600")] = "pos_colheita"
    s[s.isna() & cnae.isin(["1081301", "4621400"])] = "cafe"
    s[s.isna() & ((cnae == "1710900") | ((cnae == "0210101") & grande))] = "florestal"
    coop_cnae = cnae.str[:2].isin(["01", "10", "46"])
    s[s.isna() & (b["natureza_juridica"].astype(str) == "2143") & coop_cnae] = "cooperativa"
    b["setor"] = s
    b = b[b["setor"].notna()].copy()
    b["confirmar"] = (b["setor"] == "usina") & ~b["anp"]
    return b, excl


def setor_painel(df: pd.DataFrame) -> pd.Series:
    """O painel separa a usina validada pela ANP da que fica para confirmar."""
    s = df["setor"].copy()
    s[(df["setor"] == "usina") & df["anp"]] = "usina_anp"
    s[(df["setor"] == "usina") & ~df["anp"]] = "usina_conf"
    return s


def agregar(cls: pd.DataFrame, cap: dict[str, float]) -> pd.DataFrame:
    """Município × setor do painel: nº de estabelecimentos e capacidade ANP somada."""
    d = cls[cls["cod_municipio"].notna()].copy()
    d["setor_painel"] = setor_painel(d)
    d["cap_etanol_m3d"] = d["cnpj"].map(cap).where(d["anp"])
    ag = (d.groupby(["cod_municipio", "setor_painel"])
            .agg(estabelecimentos=("cnpj", "size"), cap_etanol_m3d=("cap_etanol_m3d", "sum"))
            .reset_index().rename(columns={"setor_painel": "setor"}))
    ag.loc[ag["setor"] != "usina_anp", "cap_etanol_m3d"] = None
    return ag


# ──────────────────────────────────────────────────────────────────────────────
# Extração (DuckDB)
# ──────────────────────────────────────────────────────────────────────────────
COLS = """e.cnpj_basico, e.cnpj_ordem, e.cnpj_dv, e.matriz_filial, e.nome_fantasia, e.cnae_principal,
          e.data_inicio, e.uf, e.municipio AS mun_rfb, m.razao_social, m.natureza_juridica,
          m.porte, m.capital_social"""


def extrair(con) -> pd.DataFrame:
    """Candidatos: ativos com CNAE da lista, mais os de natureza 2143 (cooperativa) com
    CNAE das divisões 01, 10 e 46. Filtra estabelecimentos primeiro e junta por igualdade."""
    lista = ",".join(f"'{c}'" for c in CNAE_CANDIDATOS)
    return con.execute(f"""
        WITH e AS (
          SELECT * FROM estabelecimentos
          WHERE situacao_cadastral = '02'
            AND (cnae_principal IN ({lista}) OR substr(cnae_principal, 1, 2) IN ('01', '10', '46')))
        SELECT {COLS}
        FROM e JOIN empresas m ON m.cnpj_basico = e.cnpj_basico
        WHERE e.cnae_principal IN ({lista}) OR m.natureza_juridica = '2143'
    """).df()


def extrair_por_cnpj(con, cnpjs: list[str]) -> pd.DataFrame:
    """Plantas da ANP que a Receita registra com outro CNAE: pelo CNPJ raiz (igualdade)
    e o filtro do CNPJ completo depois, em pandas."""
    if not cnpjs:
        return pd.DataFrame()
    raizes = ",".join(sorted({f"'{c[:8]}'" for c in cnpjs}))
    d = con.execute(f"""
        WITH e AS (SELECT * FROM estabelecimentos WHERE cnpj_basico IN ({raizes}))
        SELECT {COLS}, e.situacao_cadastral
        FROM e JOIN empresas m ON m.cnpj_basico = e.cnpj_basico
    """).df()
    d["cnpj"] = d["cnpj_basico"] + d["cnpj_ordem"] + d["cnpj_dv"]
    return d[d["cnpj"].isin(set(cnpjs))]


def pontos_municipios(cods: set[str]) -> dict[str, list[float]]:
    """Ponto representativo (dentro do polígono) de cada município, da malha do painel."""
    import json
    from shapely.geometry import shape
    geo = json.loads((PUBLIC_DATA / "geo_mun.json").read_text(encoding="utf-8"))
    out = {}
    for f in geo["features"]:
        c = str(f["properties"].get("cod_ibge"))
        if c in cods:
            p = shape(f["geometry"]).representative_point()
            out[c] = [round(p.y, 4), round(p.x, 4)]
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t0 = time.time()
    per = rc.periodo_atual()
    zs = sorted((RAW_DIR / "anp").glob("pb-da-etanol_*.zip"))
    if not zs:
        raise SystemExit("Arquivo da ANP ausente. Rode download/download_anp_etanol.py.")
    anp, mes_anp = ler_anp(zs[-1])
    cap = dict(zip(anp["cnpj"], anp["cap_total_m3d"]))
    print(f"ANP {mes_anp}: {len(anp)} plantas autorizadas ({zs[-1].name})")

    con = rc.conectar(per)
    base = extrair(con)
    base["cnpj"] = base["cnpj_basico"] + base["cnpj_ordem"] + base["cnpj_dv"]
    t_base = time.time() - t0
    print(f"base CNPJ {per}: {len(base):,} candidatos ativos em {t_base:.0f}s")
    falta = sorted(set(anp["cnpj"]) - set(base["cnpj"]))
    extra = extrair_por_cnpj(con, falta)
    anp_inativas = sorted(extra.loc[extra["situacao_cadastral"] != "02", "cnpj"]) if len(extra) else []
    if len(extra):
        base = pd.concat([base, extra[extra["situacao_cadastral"] == "02"].drop(columns="situacao_cadastral")],
                         ignore_index=True)
    cnaes = dict(con.execute("SELECT codigo, descricao FROM cnaes").fetchall())
    muns = dict(con.execute("SELECT codigo, descricao FROM municipios").fetchall())
    con.close()

    cls, excl = classificar(base, set(anp["cnpj"]))
    cls["municipio_rfb"] = cls["mun_rfb"].map(muns)
    pares = set(zip(cls["municipio_rfb"], cls["uf"]))
    mapa, sem = rc.casar_municipios(pares)
    cls["cod_municipio"] = [mapa.get((m, u)) for m, u in zip(cls["municipio_rfb"], cls["uf"])]
    cls["cap_etanol_m3d"] = cls["cnpj"].map(cap)
    cls["cnae_principal_desc"] = cls["cnae_principal"].map(cnaes)
    rs = cls["razao_social"].fillna("").str.upper()
    cls["alerta"] = ""
    cls.loc[rs.str.contains("RECUPERACAO JUDICIAL|RECUPERAÇÃO JUDICIAL"), "alerta"] = "em recuperação judicial"
    cls.loc[rs.str.contains("FALID|MASSA FALIDA"), "alerta"] = "falida"

    # ── validação ANP × Receita (só contagens) ──
    u = cls[cls["setor"] == "usina"]
    rfb_ind = set(u.loc[u["cnae_principal"].isin(CNAE_USINA), "cnpj"])
    anp_set, base_set = set(anp["cnpj"]), set(cls["cnpj"])
    nao_encontradas = sorted(anp_set - set(base["cnpj"]) - set(anp_inativas))
    val = {
        "periodo_rfb": per, "mes_anp": mes_anp, "arquivo_anp": zs[-1].name,
        "plantas_anp": int(len(anp)),
        "capacidade_anp_m3d": round(float(anp["cap_total_m3d"].sum())),
        "anp_ativas_na_receita": int(len(anp_set & base_set)),
        "anp_inativas_na_receita": int(len(anp_inativas)),
        "anp_nao_encontradas_na_receita": int(len(nao_encontradas)),
        "receita_cnae_de_usina": int(len(rfb_ind)),
        "receita_cnae_de_usina_e_anp": int(len(rfb_ind & anp_set)),
        "anp_com_outro_cnae_na_receita": int(len((anp_set & base_set) - rfb_ind)),
        "receita_cnae_de_usina_sem_anp_confirmar": int(len(rfb_ind - anp_set)),
        "usinas_em_recuperacao_judicial": int((u["alerta"] == "em recuperação judicial").sum()),
        "grupos_sucroenergeticos_raiz": int(u["cnpj_basico"].nunique()),
        "unidades_agricolas_de_grupo": int((cls["setor"] == "usina_agricola").sum()),
        **excl,
        "sem_municipio_ibge": int(cls["cod_municipio"].isna().sum()),
        "municipios_rfb_sem_par": [f"{n} ({u_})" for n, u_ in sem],
    }

    # ── saídas ──
    cache = rc.pf_cache_dir()
    det_cols = ["setor", "cnpj", "cnpj_basico", "matriz_filial", "razao_social", "nome_fantasia",
                "cnae_principal", "cnae_principal_desc", "porte", "natureza_juridica", "capital",
                "data_inicio", "uf", "municipio_rfb", "cod_municipio", "anp", "cap_etanol_m3d",
                "confirmar", "alerta"]
    det = cls[det_cols].sort_values(["setor", "cod_municipio", "razao_social"])
    det.to_parquet(cache / f"contas_chave_detalhe_{per}.parquet", index=False)

    ag = agregar(cls, cap)
    ag["periodo_rfb"] = per
    outs = save_table(ag, PROCESSED_DIR / "municipality" / "contas_chave_municipio")

    pts = pontos_municipios(set(ag["cod_municipio"]))
    mun = {}
    for r in ag.itertuples(index=False):
        o = mun.setdefault(r.cod_municipio, {"xy": pts.get(r.cod_municipio)})
        o[r.setor] = int(r.estabelecimentos)
        if r.setor == "usina_anp" and pd.notna(r.cap_etanol_m3d) and r.cap_etanol_m3d > 0:
            o["cap"] = round(float(r.cap_etanol_m3d))
    sem_ponto = [c for c, o in mun.items() if not o["xy"]]
    totais = {k: int(ag.loc[ag["setor"] == k, "estabelecimentos"].sum()) for k in SETORES}
    obj = {
        "fonte": "Receita Federal, Dados Abertos CNPJ (estabelecimentos ativos, CNAE principal, natureza 2xxx); "
                 "ANP, Painel Dinâmico de Produtores de Etanol (capacidade autorizada)",
        "periodo_rfb": per, "mes_anp": mes_anp, "gerado_em": now_iso(),
        "setores": {k: {"rot": r, "cor": c} for k, (r, c) in SETORES.items()},
        "cautelas": CAUTELAS,
        "validacao": {k: v for k, v in val.items() if not isinstance(v, list)},
        "totais": totais,
        "mun": mun,
    }
    pub = write_public_json(PUBLIC_DATA / "contas_chave.json", obj)
    write_manifest("contas_chave", source=f"Receita Federal CNPJ {per}; ANP {mes_anp}",
                   reference_date=per, source_files=[str(zs[-1])], row_count=len(cls),
                   municipality_count=len(mun), warnings=[f"sem ponto: {c}" for c in sem_ponto],
                   output_files=outs + [str(pub)], extra={"validacao": val, "totais": totais})

    print(f"\nclassificados: {len(cls):,} estabelecimentos em {len(mun):,} municípios · "
          f"{pub.stat().st_size / 1_048_576:.2f} MB · {time.time() - t0:.0f}s")
    for k, v in totais.items():
        print(f"  {k:15s} {v:6,d}")
    for k, v in val.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
