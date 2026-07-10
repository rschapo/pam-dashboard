"""
PPM IBGE - Download de dados de pecuaria municipal (rebanho + producao)
Mesmo padrao do download_pam_ibge.py: 1 estado por vez, salvamento
progressivo por ano/tabela, retomada automatica se interrompido.

Fontes (confirmadas via API de metadados do IBGE):
  Tabela 3939 - Efetivo dos rebanhos (cabecas), classif c79
  Tabela 74   - Producao de origem animal (quantidade + valor), classif c80

Run from the project root:
    py generator/download_ppm_ibge.py
"""

import sys, os, time, requests, pandas as pd
from tqdm import tqdm

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── Configuracoes ──────────────────────────────────────────────────────────
ANO_INICIO  = 2004
ANO_FIM     = 2024
PASTA_SAIDA = r"C:\Users\schap\Downloads\IBGE\dados_ppm"
PASTA_RAW   = os.path.join(PASTA_SAIDA, "raw")
PAUSA_REQ   = 0.8
MAX_TENT    = 3
TIMEOUT_SEG = 90

TABELAS = [
    {"tabela": 3939, "classif": "c79", "tipo": "Rebanho",
     "variaveis": {"105": "Efetivo_Cabecas"}},
    {"tabela": 74, "classif": "c80", "tipo": "Producao",
     "variaveis": {"106": "Quantidade", "215": "Valor_mil_reais"}},
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

# ── API ─────────────────────────────────────────────────────────────────────

def requisitar(tabela, classif, variaveis, estado_cod, ano):
    variaveis_str = ",".join(variaveis.keys())
    url = (
        f"https://apisidra.ibge.gov.br/values"
        f"/t/{tabela}/n6/in%20n3%20{estado_cod}"
        f"/v/{variaveis_str}/p/{ano}/{classif}/allxt"
    )
    for tent in range(1, MAX_TENT + 1):
        try:
            r = requests.get(url, timeout=TIMEOUT_SEG)
            if r.status_code == 400: return []
            if r.status_code == 429:
                time.sleep(60); continue
            r.raise_for_status()
            return r.json()
        except Exception:
            if tent == MAX_TENT: return []
            time.sleep(5 * tent)
    return []


def detectar_ultimo_ano():
    print("Detectando ultimo ano disponivel...")
    for ano in range(ANO_FIM, ANO_INICIO - 1, -1):
        url = f"https://apisidra.ibge.gov.br/values/t/3939/n3/11/v/105/p/{ano}/c79/2670"
        try:
            r = requests.get(url, timeout=20)
            d = r.json()
            if len(d) > 1 and d[1].get("V","").strip() not in ("","...","-"):
                print(f"  -> Ultimo ano: {ano}")
                return ano
        except: pass
        time.sleep(0.4)
    return ANO_FIM - 1


# ── Parsing ─────────────────────────────────────────────────────────────────

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
    col_cc = achar(lambda v: ("rebanho" in v.lower() or "produto" in v.lower()) and "digo" in v) or "D4C"
    col_cn = achar(lambda v: ("rebanho" in v.lower() or "produto" in v.lower()) and "Nome" in v) or "D4N"

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
            "Variavel"     : variaveis.get(cod_var, cod_var),
            "Valor"        : limpar(row.get("V", "")),
        })
    return pd.DataFrame(linhas)


# ── Download com salvamento progressivo ─────────────────────────────────────

def caminho_raw(tabela, ano):
    return os.path.join(PASTA_RAW, f"ppm_{tabela}_{ano}.csv")


def baixar_tabela(tabela, classif, tipo, variaveis, ultimo_ano):
    anos = list(range(ANO_INICIO, ultimo_ano + 1))

    anos_pendentes = [a for a in anos if not os.path.exists(caminho_raw(tabela, a))]
    anos_prontos   = len(anos) - len(anos_pendentes)

    print(f"\n{'='*60}")
    print(f"Tabela {tabela} ({tipo}) | {ANO_INICIO}-{ultimo_ano}")
    if anos_prontos:
        print(f"  Retomando: {anos_prontos} anos ja baixados, {len(anos_pendentes)} restantes")
    print(f"{'='*60}")

    if not anos_pendentes:
        print("  Todos os anos ja estao baixados. Pulando download.")
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


def pivotar(df, variaveis):
    if df.empty: return df
    idx = ["Cod_Municipio","Municipio","UF","Regiao","Ano",
           "Tipo","Cod_Categoria","Categoria"]
    pv = df.pivot_table(
        index=idx, columns="Variavel", values="Valor", aggfunc="first"
    ).reset_index()
    pv.columns.name = None
    for col in variaveis.values():
        if col not in pv.columns:
            pv[col] = None
    return pv


def carregar_tabela(tabela, ultimo_ano, variaveis):
    anos  = list(range(ANO_INICIO, ultimo_ano + 1))
    files = [caminho_raw(tabela, a) for a in anos if os.path.exists(caminho_raw(tabela, a))]
    if not files: return pd.DataFrame()
    frames = []
    for f in files:
        try:
            df = pd.read_csv(f, sep=";", encoding="utf-8-sig", dtype={"Cod_Municipio": str})
            if not df.empty:
                frames.append(df)
        except: pass
    if not frames: return pd.DataFrame()
    return pivotar(pd.concat(frames, ignore_index=True), variaveis)


# ── Exportacao ──────────────────────────────────────────────────────────────

def salvar_csv(df, nome):
    p = os.path.join(PASTA_SAIDA, nome)
    df.to_csv(p, index=False, encoding="utf-8-sig", sep=";")
    mb = os.path.getsize(p) / 1_048_576
    print(f"  [SALVO] {nome} | {len(df):,} linhas | {mb:.1f} MB")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("PPM IBGE - Download com salvamento progressivo")
    print(f"Saida: {os.path.abspath(PASTA_SAIDA)}")
    print("(Se interrompido, rode novamente para retomar)")
    print("=" * 60)

    ultimo_ano = detectar_ultimo_ano()
    if ultimo_ano < ANO_INICIO:
        ultimo_ano = ANO_FIM

    n_anos = len(range(ANO_INICIO, ultimo_ano + 1))
    n_req  = n_anos * len(ESTADOS) * len(TABELAS)
    est_min = round(n_req * (PAUSA_REQ + 0.5) / 60)
    print(f"\nTotal: {n_req} requisicoes | ~{est_min} min")

    # ── 1. Download (com retomada automatica)
    for cfg in TABELAS:
        baixar_tabela(cfg["tabela"], cfg["classif"], cfg["tipo"], cfg["variaveis"], ultimo_ano)

    # ── 2. Consolidar e exportar
    print("\nConsolidando dados...")
    dfs = {cfg["tipo"]: carregar_tabela(cfg["tabela"], ultimo_ano, cfg["variaveis"]) for cfg in TABELAS}

    if all(d.empty for d in dfs.values()):
        print("[X] Nenhum dado disponivel.")
        return

    df_total = pd.concat([d for d in dfs.values() if not d.empty], ignore_index=True)

    print(f"\n{'='*60}")
    print("Salvando arquivos finais...")
    if not dfs["Rebanho"].empty:  salvar_csv(dfs["Rebanho"],  "PPM_municipios_rebanho.csv")
    if not dfs["Producao"].empty: salvar_csv(dfs["Producao"], "PPM_municipios_producao.csv")
    salvar_csv(df_total, "PPM_municipios_completo.csv")

    print("\n" + "=" * 60)
    print("[CONCLUIDO]")
    print(f"  Linhas totais : {len(df_total):,}")
    print(f"  Municipios    : {df_total['Cod_Municipio'].nunique():,}")
    print(f"  Categorias    : {df_total['Categoria'].nunique():,}")
    print(f"  Anos          : {df_total['Ano'].min()} - {df_total['Ano'].max()}")
    print(f"  Arquivos em   : {os.path.abspath(PASTA_SAIDA)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
