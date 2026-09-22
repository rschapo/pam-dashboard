"""
PAM IBGE - Download de dados agricolas municipais
Versao com salvamento progressivo e retomada automatica.
Baixa 1 estado por vez. Se interrompido, retoma do ponto parado.
"""

import sys, os, time, requests, pandas as pd
from pathlib import Path
from tqdm import tqdm

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── Configuracoes ──────────────────────────────────────────────────────────
ANO_INICIO  = 2004
ANO_FIM     = 2025
# Raiz dos brutos IBGE do projeto: .../pam-dashboard/data/raw/ibge
RAW_IBGE = Path(__file__).resolve().parent.parent / "data" / "raw" / "ibge"
PASTA_SAIDA = str(RAW_IBGE / "pam")
PASTA_RAW   = os.path.join(PASTA_SAIDA, "raw")   # CSVs parciais por ano/tabela
PAUSA_REQ   = 0.8
MAX_TENT    = 3
TIMEOUT_SEG = 90

VARIAVEIS = {
    "109": "Area_Plantada_ha",
    "216": "Area_Colhida_ha",
    "214": "Quantidade_Produzida_ton",
    "112": "Rendimento_Medio_kg_ha",
    "215": "Valor_Producao_mil_reais",
}

COL_RENDIMENTO = "Rendimento_Medio_kg_ha"

TABELAS = [
    {"tabela": 1612, "classif": "c81", "tipo": "Temporaria"},
    {"tabela": 1613, "classif": "c82", "tipo": "Permanente"},
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

def _requisitar_uma_variavel(tabela, classif, var_cod, estado_cod, ano):
    url = (
        f"https://apisidra.ibge.gov.br/values"
        f"/t/{tabela}/n6/in%20n3%20{estado_cod}"
        f"/v/{var_cod}/p/{ano}/{classif}/allxt"
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


def requisitar(tabela, classif, estado_cod, ano):
    """Busca UMA variavel por vez -- estados grandes (SP, MG, PR, RS, BA) excedem
    o limite de 50.000 valores da API SIDRA quando as 5 variaveis sao pedidas
    juntas (allxt = todas as culturas), causando HTTP 400 tratado como "sem
    dado" -- foi a causa raiz do gap de 5 estados no historico 2004-2024,
    corrigido aqui de forma definitiva (nao so remendado para os anos ja
    baixados)."""
    cabecalho = None
    linhas = []
    for var_cod in VARIAVEIS.keys():
        resp = _requisitar_uma_variavel(tabela, classif, var_cod, estado_cod, ano)
        if not resp or len(resp) < 2:
            continue
        if cabecalho is None:
            cabecalho = resp[0]
        linhas.extend(resp[1:])
        time.sleep(PAUSA_REQ)
    if not linhas:
        return []
    return [cabecalho] + linhas


def detectar_ultimo_ano():
    print("Detectando ultimo ano disponivel...")
    for ano in range(ANO_FIM, ANO_INICIO - 1, -1):
        url = f"https://apisidra.ibge.gov.br/values/t/1612/n3/11/v/216/p/{ano}/c81/2713"
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


def parsear(dados, tipo, uf):
    if len(dados) < 2: return pd.DataFrame()
    cab = dados[0]

    def achar(fn):
        return next((k for k,v in cab.items() if fn(v)), None)

    col_mc = achar(lambda v: "Munic" in v and "digo" in v) or "D1C"
    col_mn = achar(lambda v: "Munic" in v and "Nome"  in v) or "D1N"
    col_vc = achar(lambda v: "Vari"  in v and "digo"  in v) or "D2C"
    col_an = achar(lambda v: "Ano"   in v and "Nome"  in v) or "D3N"
    col_cc = achar(lambda v: "lavoura" in v.lower() and "digo" in v) or "D4C"
    col_cn = achar(lambda v: "lavoura" in v.lower() and "Nome" in v) or "D4N"

    linhas = []
    for row in dados[1:]:
        cod_var = str(row.get(col_vc, ""))
        linhas.append({
            "Cod_Municipio": row.get(col_mc, ""),
            "Municipio"    : row.get(col_mn, ""),
            "UF"           : uf,
            "Regiao"       : REGIAO_UF.get(uf, "??"),
            "Ano"          : row.get(col_an, ""),
            "Tipo_Lavoura" : tipo,
            "Cod_Cultura"  : row.get(col_cc, ""),
            "Cultura"      : row.get(col_cn, ""),
            "Variavel"     : VARIAVEIS.get(cod_var, cod_var),
            "Valor"        : limpar(row.get("V", "")),
        })
    return pd.DataFrame(linhas)


# ── Download com salvamento progressivo ─────────────────────────────────────

def caminho_raw(tabela, ano):
    return os.path.join(PASTA_RAW, f"pam_{tabela}_{ano}.csv")


def baixar_tabela(tabela, classif, tipo, ultimo_ano):
    anos = list(range(ANO_INICIO, ultimo_ano + 1))

    # Detectar quais anos ja foram baixados
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
                dados = requisitar(tabela, classif, cod_est, ano)
                if dados and len(dados) > 1:
                    df_bloco = parsear(dados, tipo, uf)
                    if not df_bloco.empty:
                        frames_ano.append(df_bloco)
                barra.update(1)
                barra.set_postfix(ano=ano, uf=uf, refresh=False)
                time.sleep(PAUSA_REQ)

            # Salvar CSV deste ano imediatamente
            if frames_ano:
                df_ano = pd.concat(frames_ano, ignore_index=True)
                df_ano.to_csv(caminho_raw(tabela, ano), index=False,
                              encoding="utf-8-sig", sep=";")
                tqdm.write(f"  [SALVO] {tabela}/{ano}: {len(df_ano):,} linhas")
            else:
                # Criar arquivo vazio para nao re-baixar
                pd.DataFrame().to_csv(caminho_raw(tabela, ano), index=False)
                tqdm.write(f"  [-]  {tabela}/{ano}: sem dados")


def pivotar(df):
    if df.empty: return df
    idx = ["Cod_Municipio","Municipio","UF","Regiao","Ano",
           "Tipo_Lavoura","Cod_Cultura","Cultura"]
    pv = df.pivot_table(
        index=idx, columns="Variavel", values="Valor", aggfunc="first"
    ).reset_index()
    pv.columns.name = None
    for col in VARIAVEIS.values():
        if col not in pv.columns:
            pv[col] = None
    return pv


def carregar_tabela(tabela, ultimo_ano):
    """Le todos os CSVs parciais de uma tabela e retorna DataFrame consolidado."""
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
    return pivotar(pd.concat(frames, ignore_index=True))


# ── Exportacao ──────────────────────────────────────────────────────────────

def agregar(df, chaves, cols_num):
    # Rendimento e uma razao: soma numerador e denominador e so entao divide.
    # Soma-lo direto daria a soma dos rendimentos municipais, sem significado fisico.
    cols_soma = [c for c in cols_num if c != COL_RENDIMENTO]
    out = df.groupby(chaves)[cols_soma].sum(min_count=1).reset_index()
    if {"Quantidade_Produzida_ton", "Area_Colhida_ha"} <= set(out.columns):
        area = out["Area_Colhida_ha"]
        out[COL_RENDIMENTO] = (out["Quantidade_Produzida_ton"] / area * 1000).where(area > 0).round(1)
    return out[chaves + cols_num]


def salvar_csv(df, nome):
    p = os.path.join(PASTA_SAIDA, nome)
    df.to_csv(p, index=False, encoding="utf-8-sig", sep=";")
    mb = os.path.getsize(p) / 1_048_576
    print(f"  [SALVO] {nome} | {len(df):,} linhas | {mb:.1f} MB")


def criar_excel(dfs):
    p = os.path.join(PASTA_SAIDA, "PAM_completo.xlsx")
    print("\nCriando PAM_completo.xlsx...")
    with pd.ExcelWriter(p, engine="openpyxl") as w:
        for aba, df in dfs.items():
            if not df.empty:
                df.head(1_000_000).to_excel(w, sheet_name=aba, index=False)
    print(f"  [SALVO] PAM_completo.xlsx | {os.path.getsize(p)/1_048_576:.1f} MB")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("PAM IBGE - Download com salvamento progressivo")
    print(f"Saida: {os.path.abspath(PASTA_SAIDA)}")
    print("(Se interrompido, rode novamente para retomar)")
    print("=" * 60)

    ultimo_ano = detectar_ultimo_ano()
    if ultimo_ano < ANO_INICIO:
        ultimo_ano = ANO_FIM

    n_anos = len(range(ANO_INICIO, ultimo_ano + 1))
    n_req  = n_anos * len(ESTADOS) * 2
    est_min = round(n_req * (PAUSA_REQ + 0.5) / 60)
    print(f"\nTotal: {n_req} requisicoes | ~{est_min} min")

    # ── 1. Download (com retomada automatica)
    for cfg in TABELAS:
        baixar_tabela(cfg["tabela"], cfg["classif"], cfg["tipo"], ultimo_ano)

    # ── 2. Consolidar e exportar
    print("\nConsolidando dados...")
    df_temp = carregar_tabela(1612, ultimo_ano)
    df_perm = carregar_tabela(1613, ultimo_ano)

    if df_temp.empty and df_perm.empty:
        print("[X] Nenhum dado disponivel.")
        return

    df_total = pd.concat([df_temp, df_perm], ignore_index=True)
    cols_num = [c for c in VARIAVEIS.values() if c in df_total.columns]

    df_est = agregar(df_total, ["UF","Regiao","Ano","Tipo_Lavoura","Cod_Cultura","Cultura"], cols_num)
    df_bra = agregar(df_total, ["Ano","Tipo_Lavoura","Cod_Cultura","Cultura"], cols_num)

    df_dic = pd.DataFrame([
        {"Campo":"Cod_Municipio",            "Descricao":"Codigo IBGE do municipio (7 digitos)"},
        {"Campo":"Municipio",                "Descricao":"Nome do municipio"},
        {"Campo":"UF",                       "Descricao":"Sigla do estado"},
        {"Campo":"Regiao",                   "Descricao":"Grande regiao"},
        {"Campo":"Ano",                      "Descricao":"Ano de referencia"},
        {"Campo":"Tipo_Lavoura",             "Descricao":"Temporaria ou Permanente"},
        {"Campo":"Cod_Cultura",              "Descricao":"Codigo IBGE da cultura"},
        {"Campo":"Cultura",                  "Descricao":"Nome da cultura"},
        {"Campo":"Area_Plantada_ha",         "Descricao":"Area plantada (ha) - var 109"},
        {"Campo":"Area_Colhida_ha",          "Descricao":"Area colhida (ha) - var 216"},
        {"Campo":"Quantidade_Produzida_ton", "Descricao":"Quantidade produzida (ton) - var 214"},
        {"Campo":"Rendimento_Medio_kg_ha",   "Descricao":"Rendimento medio (kg/ha) - var 112"},
        {"Campo":"Valor_Producao_mil_reais", "Descricao":"Valor da producao (mil R$) - var 215"},
        {"Campo":"Fonte",                    "Descricao":"IBGE PAM - SIDRA tabelas 1612 e 1613"},
    ])

    print(f"\n{'='*60}")
    print("Salvando arquivos finais...")
    if not df_temp.empty: salvar_csv(df_temp, "PAM_municipios_temporarias.csv")
    if not df_perm.empty: salvar_csv(df_perm, "PAM_municipios_permanentes.csv")
    salvar_csv(df_total, "PAM_municipios_completo.csv")
    salvar_csv(df_est,   "PAM_estados.csv")
    salvar_csv(df_bra,   "PAM_brasil.csv")
    salvar_csv(df_dic,   "dicionario_dados.csv")

    criar_excel({
        "Temporarias": df_temp,
        "Permanentes": df_perm,
        "Por_Estado" : df_est,
        "Brasil"     : df_bra,
        "Dicionario" : df_dic,
    })

    print("\n" + "=" * 60)
    print("[CONCLUIDO]")
    print(f"  Linhas totais : {len(df_total):,}")
    print(f"  Municipios    : {df_total['Cod_Municipio'].nunique():,}")
    print(f"  Culturas      : {df_total['Cultura'].nunique():,}")
    print(f"  Anos          : {df_total['Ano'].min()} - {df_total['Ano'].max()}")
    print(f"  Arquivos em   : {os.path.abspath(PASTA_SAIDA)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
