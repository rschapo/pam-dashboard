"""
PEVS IBGE — Download da Produção da Extração Vegetal e da Silvicultura (municipal).
Mesmo padrão do download_ppm_ibge.py: 1 estado por vez, salvamento progressivo
por ano/tabela, retomada automática se interrompido.

Cobre as três tabelas SIDRA da PEVS:
  Tabela 291  — Silvicultura: quantidade produzida + valor da produção, por produto
  Tabela 289  — Extração vegetal (nativa): quantidade produzida + valor, por produto
  Tabela 5930 — Área total existente da silvicultura, por espécie florestal

Os códigos de variável e de classificação NÃO são fixos no arquivo: são
descobertos em tempo de execução na API de metadados do IBGE (v3/agregados),
o que deixa o coletor robusto a mudanças de numeração. A silvicultura é a "terceira
perna" do tripé do IBGE ao lado do PAM (lavouras) e da PPM (pecuária).

Rodar a partir da raiz do projeto (na sua máquina — o IBGE não é alcançável em
ambientes com allowlist de rede):
    py generator/download_pevs_ibge.py
"""

import sys, os, time, requests, pandas as pd
from pathlib import Path
from tqdm import tqdm

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── Configurações ────────────────────────────────────────────────────────────
ANO_INICIO  = 2004
ANO_FIM     = 2024
# Raiz dos brutos IBGE do projeto: .../pam-dashboard/data/raw/ibge
RAW_IBGE = Path(__file__).resolve().parent.parent / "data" / "raw" / "ibge"
PASTA_SAIDA = str(RAW_IBGE / "pevs")
PASTA_RAW   = os.path.join(PASTA_SAIDA, "raw")
PAUSA_REQ   = 0.8
MAX_TENT    = 3
TIMEOUT_SEG = 90
API_META    = "https://servicodados.ibge.gov.br/api/v3/agregados"

# Uma linha por tabela. As variáveis/classificação são descobertas por metadados;
# 'metricas' diz quais métricas essa tabela fornece e como mapeá-las (q/v/a).
#   q = quantidade produzida | v = valor da produção (mil R$) | a = área (ha)
TABELAS = [
    {"tabela": 291,  "tipo": "Silvicultura",     "metricas": {"q": "Quantidade produzida",
                                                               "v": "Valor da produção"}},
    {"tabela": 289,  "tipo": "Extracao",         "metricas": {"q": "Quantidade produzida",
                                                               "v": "Valor da produção"}},
    {"tabela": 5930, "tipo": "AreaSilvicultura", "metricas": {"a": "Área"}},
]

ESTADOS = [11,12,13,14,15,16,17,21,22,23,24,25,26,27,28,29,
           31,32,33,35,41,42,43,50,51,52,53]

SIGLA_UF = {
    11:"RO",12:"AC",13:"AM",14:"RR",15:"PA",16:"AP",17:"TO",
    21:"MA",22:"PI",23:"CE",24:"RN",25:"PB",26:"PE",27:"AL",28:"SE",29:"BA",
    31:"MG",32:"ES",33:"RJ",35:"SP",41:"PR",42:"SC",43:"RS",
    50:"MS",51:"MT",52:"GO",53:"DF",
}

REGIAO_UF = {
    "RO":"Norte","AC":"Norte","AM":"Norte","RR":"Norte","PA":"Norte","AP":"Norte","TO":"Norte",
    "MA":"Nordeste","PI":"Nordeste","CE":"Nordeste","RN":"Nordeste","PB":"Nordeste",
    "PE":"Nordeste","AL":"Nordeste","SE":"Nordeste","BA":"Nordeste",
    "MG":"Sudeste","ES":"Sudeste","RJ":"Sudeste","SP":"Sudeste",
    "PR":"Sul","SC":"Sul","RS":"Sul",
    "MS":"Centro-Oeste","MT":"Centro-Oeste","GO":"Centro-Oeste","DF":"Centro-Oeste",
}

os.makedirs(PASTA_SAIDA, exist_ok=True)
os.makedirs(PASTA_RAW,   exist_ok=True)


# ── Descoberta de metadados (variáveis + classificação + anos) ───────────────

def descobrir_metadados(tabela, metricas):
    """
    Lê a API de metadados e devolve:
      variaveis: {cod_variavel(str): metrica('q'/'v'/'a')}
      classif  : 'c<id>' da classificação de produto/espécie (ou None)
    Casa cada métrica pedida com a variável cujo nome contém o texto-chave.
    """
    url = f"{API_META}/{tabela}/metadados"
    r = requests.get(url, timeout=TIMEOUT_SEG)
    r.raise_for_status()
    meta = r.json()

    variaveis = {}
    for metrica, chave in metricas.items():
        chave_l = chave.lower()
        alvo = None
        for v in meta.get("variaveis", []):
            nome = str(v.get("nome", "")).lower()
            # normaliza acento de "área"
            nome_norm = nome.replace("á", "a").replace("ã", "a")
            chave_norm = chave_l.replace("á", "a").replace("ã", "a")
            if chave_norm in nome_norm:
                alvo = str(v.get("id"))
                break
        if alvo:
            variaveis[alvo] = metrica
        else:
            print(f"    [AVISO] tabela {tabela}: variável para '{chave}' não encontrada nos metadados")

    # classificação de produto/espécie: a PEVS traz exatamente uma por tabela.
    classif = None
    classes = meta.get("classificacoes", [])
    if classes:
        classif = f"c{classes[0]['id']}"

    nome_tab = meta.get("nome", "")
    print(f"    tabela {tabela}: {nome_tab[:70]}")
    print(f"      variáveis={variaveis}  classif={classif}")
    return variaveis, classif


def descobrir_anos(tabela):
    """Anos disponíveis para a tabela, limitados à janela [ANO_INICIO, ANO_FIM]."""
    url = f"{API_META}/{tabela}/periodos"
    try:
        r = requests.get(url, timeout=TIMEOUT_SEG)
        r.raise_for_status()
        anos = sorted(int(p["id"]) for p in r.json() if str(p.get("id", "")).isdigit())
        anos = [a for a in anos if ANO_INICIO <= a <= ANO_FIM]
        if anos:
            print(f"      anos disponíveis: {anos[0]}–{anos[-1]} ({len(anos)})")
            return anos
    except Exception as e:
        print(f"    [AVISO] períodos da tabela {tabela} indisponíveis ({e}); usando janela padrão")
    return list(range(ANO_INICIO, ANO_FIM + 1))


# ── API de valores ───────────────────────────────────────────────────────────

def requisitar(tabela, classif, variaveis, estado_cod, ano):
    variaveis_str = ",".join(variaveis.keys())
    classif_path = f"/{classif}/all" if classif else ""
    url = (
        f"https://apisidra.ibge.gov.br/values"
        f"/t/{tabela}/n6/in%20n3%20{estado_cod}"
        f"/v/{variaveis_str}/p/{ano}{classif_path}"
    )
    for tent in range(1, MAX_TENT + 1):
        try:
            r = requests.get(url, timeout=TIMEOUT_SEG)
            if r.status_code == 400: return []      # sem dado p/ o recorte
            if r.status_code == 429:
                time.sleep(60); continue
            r.raise_for_status()
            return r.json()
        except Exception:
            if tent == MAX_TENT: return []
            time.sleep(5 * tent)
    return []


# ── Parsing ───────────────────────────────────────────────────────────────────

def limpar(v):
    if v is None: return None
    v = str(v).strip()
    if v in ("-","..","...","X","","nd"): return None
    try: return float(v.replace(",",""))
    except: return None


def parsear(dados, tipo, uf, variaveis):
    if len(dados) < 2: return pd.DataFrame()
    cab = dados[0]

    def achar(fn):
        return next((k for k,v in cab.items() if fn(v)), None)

    col_mc = achar(lambda v: "Munic" in v and "digo" in v) or "D1C"
    col_mn = achar(lambda v: "Munic" in v and "Nome"  in v) or "D1N"
    col_vc = achar(lambda v: "Vari"  in v and "digo"  in v) or "D2C"
    col_an = achar(lambda v: "Ano"   in v and "Nome"  in v) or "D3N"
    # classificação de produto/espécie (nome varia: "produto da silvicultura",
    # "produto extrativo", "espécie florestal") — pega o D*C/D*N remanescente
    col_cc = achar(lambda v: ("produto" in v.lower() or "esp" in v.lower()) and "digo" in v) or "D4C"
    col_cn = achar(lambda v: ("produto" in v.lower() or "esp" in v.lower()) and "Nome" in v) or "D4N"
    col_un = achar(lambda v: "Unidade de Medida" in v and "Nome" in v)

    linhas = []
    for row in dados[1:]:
        cod_var = str(row.get(col_vc, ""))
        linhas.append({
            "Cod_Municipio": row.get(col_mc, ""),
            "Municipio"    : row.get(col_mn, ""),
            "UF"           : uf,
            "Regiao"       : REGIAO_UF.get(uf, "??"),
            "Ano"          : row.get(col_an, ""),
            "Tipo"         : tipo,
            "Cod_Categoria": row.get(col_cc, ""),
            "Categoria"    : row.get(col_cn, ""),
            "Unidade"      : row.get(col_un, "") if col_un else "",
            "Metrica"      : variaveis.get(cod_var, cod_var),
            "Valor"        : limpar(row.get("V", "")),
        })
    return pd.DataFrame(linhas)


# ── Download com salvamento progressivo ──────────────────────────────────────

def caminho_raw(tabela, ano):
    return os.path.join(PASTA_RAW, f"pevs_{tabela}_{ano}.csv")


def baixar_tabela(cfg):
    tabela, tipo, metricas = cfg["tabela"], cfg["tipo"], cfg["metricas"]
    print(f"\n{'='*64}")
    print(f"Tabela {tabela} ({tipo})")
    print(f"{'='*64}")

    variaveis, classif = descobrir_metadados(tabela, metricas)
    if not variaveis:
        print(f"  [X] Sem variáveis identificadas; pulando tabela {tabela}.")
        return
    anos = descobrir_anos(tabela)
    cfg["_variaveis"], cfg["_classif"], cfg["_anos"] = variaveis, classif, anos

    anos_pendentes = [a for a in anos if not os.path.exists(caminho_raw(tabela, a))]
    anos_prontos   = len(anos) - len(anos_pendentes)
    if anos_prontos:
        print(f"  Retomando: {anos_prontos} anos já baixados, {len(anos_pendentes)} restantes")
    if not anos_pendentes:
        print("  Todos os anos já estão baixados. Pulando download.")
        return

    total_req = len(anos_pendentes) * len(ESTADOS)
    with tqdm(total=total_req, desc=f"Tab {tabela}", unit="req") as barra:
        for ano in anos_pendentes:
            frames_ano = []
            for cod_est in ESTADOS:
                uf = SIGLA_UF[cod_est]
                dados = requisitar(tabela, classif, variaveis, cod_est, ano)
                if dados and len(dados) > 1:
                    df_bloco = parsear(dados, tipo, uf, variaveis)
                    if not df_bloco.empty:
                        frames_ano.append(df_bloco)
                barra.update(1)
                barra.set_postfix(ano=ano, uf=uf, refresh=False)
                time.sleep(PAUSA_REQ)

            if frames_ano:
                df_ano = pd.concat(frames_ano, ignore_index=True)
                df_ano.to_csv(caminho_raw(tabela, ano), index=False,
                              encoding="utf-8-sig", sep=";")
                tqdm.write(f"  [SALVO] {tabela}/{ano}: {len(df_ano):,} linhas")
            else:
                pd.DataFrame().to_csv(caminho_raw(tabela, ano), index=False)
                tqdm.write(f"  [-]  {tabela}/{ano}: sem dados")


def pivotar(df):
    """Espalha a coluna Metrica (q/v/a) em colunas próprias."""
    if df.empty: return df
    idx = ["Cod_Municipio","Municipio","UF","Regiao","Ano",
           "Tipo","Cod_Categoria","Categoria","Unidade"]
    # IMPORTANTE: o SIDRA pode não retornar coluna de unidade -> 'Unidade' vem vazia (NaN).
    # Com NaN no índice, o pivot_table (dropna=True padrão) descarta TODAS as linhas.
    # Preenche os campos de índice vazios antes de pivotar.
    for c in idx:
        if c in df.columns:
            df[c] = df[c].fillna("")
    pv = df.pivot_table(index=idx, columns="Metrica", values="Valor",
                        aggfunc="first", dropna=False).reset_index()
    pv.columns.name = None
    for col in ("q","v","a"):
        if col not in pv.columns:
            pv[col] = None
    return pv


def carregar_tabela(cfg):
    tabela = cfg["tabela"]
    anos = cfg.get("_anos", list(range(ANO_INICIO, ANO_FIM + 1)))
    files = [caminho_raw(tabela, a) for a in anos if os.path.exists(caminho_raw(tabela, a))]
    frames = []
    for f in files:
        try:
            df = pd.read_csv(f, sep=";", encoding="utf-8-sig", dtype={"Cod_Municipio": str})
            if not df.empty:
                frames.append(df)
        except Exception:
            pass
    if not frames: return pd.DataFrame()
    return pivotar(pd.concat(frames, ignore_index=True))


# ── Exportação ────────────────────────────────────────────────────────────────

def salvar_csv(df, nome):
    p = os.path.join(PASTA_SAIDA, nome)
    df.to_csv(p, index=False, encoding="utf-8-sig", sep=";")
    mb = os.path.getsize(p) / 1_048_576
    print(f"  [SALVO] {nome} | {len(df):,} linhas | {mb:.1f} MB")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 64)
    print("PEVS IBGE — Download com salvamento progressivo (Silvicultura + Extração)")
    print(f"Saída: {os.path.abspath(PASTA_SAIDA)}")
    print("(Se interrompido, rode novamente para retomar)")
    print("=" * 64)

    # 1. Download (com retomada automática) + descoberta de metadados por tabela
    for cfg in TABELAS:
        baixar_tabela(cfg)

    # 2. Consolidar e exportar
    print("\nConsolidando dados…")
    dfs = {cfg["tipo"]: carregar_tabela(cfg) for cfg in TABELAS}

    if all(d.empty for d in dfs.values()):
        print("[X] Nenhum dado disponível.")
        return

    mapa_nome = {"Silvicultura": "PEVS_silvicultura.csv",
                 "Extracao": "PEVS_extracao_vegetal.csv",
                 "AreaSilvicultura": "PEVS_area_silvicultura.csv"}
    for tipo, df in dfs.items():
        if not df.empty:
            salvar_csv(df, mapa_nome[tipo])

    df_total = pd.concat([d for d in dfs.values() if not d.empty], ignore_index=True)
    salvar_csv(df_total, "PEVS_municipios_completo.csv")

    print("\n" + "=" * 64)
    print("[CONCLUÍDO]")
    print(f"  Linhas totais : {len(df_total):,}")
    print(f"  Municípios    : {df_total['Cod_Municipio'].nunique():,}")
    print(f"  Categorias    : {df_total['Categoria'].nunique():,}")
    print(f"  Anos          : {df_total['Ano'].min()} - {df_total['Ano'].max()}")
    print(f"  Arquivos em   : {os.path.abspath(PASTA_SAIDA)}")
    print("=" * 64)


if __name__ == "__main__":
    main()
