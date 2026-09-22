"""
Correcao pontual: BA, MG, SP, PR, RS estavam com truncamento PARCIAL no
periodo 2004-2024 (a correcao anterior so tratava a falha total/HTTP 400,
nao a perda silenciosa de parte das culturas quando a requisicao com as
5 variaveis juntas chegava perto do limite de 50.000 valores da API SIDRA
sem estoura-lo). Este script reaproveita as funcoes de download_pam_ibge.py
(ja corrigidas para buscar 1 variavel por vez) para re-baixar SOMENTE esses
5 estados nesses anos, substitui as linhas correspondentes nos CSVs brutos
por ano/tabela ja existentes, e deixa o pipeline pronto para o
download_pam_ibge.py original apenas reconsolidar (sem rebaixar nada, pois
todos os arquivos de ano ja existirao).
"""
import os, sys, time
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import download_pam_ibge as dl

ESTADOS_AFETADOS = {29: "BA", 31: "MG", 35: "SP", 41: "PR", 43: "RS"}
ANO_INICIO, ANO_FIM_PATCH = 2004, 2024

def main():
    print("=" * 60)
    print("Corrigindo truncamento parcial: BA/MG/SP/PR/RS, 2004-2024")
    print("=" * 60)

    for cfg in dl.TABELAS:
        tabela, classif, tipo = cfg["tabela"], cfg["classif"], cfg["tipo"]
        for ano in range(ANO_INICIO, ANO_FIM_PATCH + 1):
            caminho = dl.caminho_raw(tabela, ano)
            if not os.path.exists(caminho):
                print(f"  [AVISO] {tabela}/{ano}: arquivo nao existe, pulando")
                continue

            df_existente = pd.read_csv(caminho, sep=";", encoding="utf-8-sig",
                                        dtype={"Cod_Municipio": str})
            antes = len(df_existente)
            df_resto = df_existente[~df_existente["UF"].isin(ESTADOS_AFETADOS.values())]

            frames_novos = []
            for cod_est, uf in ESTADOS_AFETADOS.items():
                dados = dl.requisitar(tabela, classif, cod_est, ano)
                if dados and len(dados) > 1:
                    df_bloco = dl.parsear(dados, tipo, uf)
                    if not df_bloco.empty:
                        frames_novos.append(df_bloco)
                time.sleep(dl.PAUSA_REQ)

            if frames_novos:
                df_novo_5 = pd.concat(frames_novos, ignore_index=True)
                df_final = pd.concat([df_resto, df_novo_5], ignore_index=True)
            else:
                df_final = df_resto

            df_final.to_csv(caminho, index=False, encoding="utf-8-sig", sep=";")
            depois = len(df_final)
            novas_5 = sum(len(f) for f in frames_novos)
            print(f"  [OK] {tabela}/{ano}: {antes:,} -> {depois:,} linhas "
                  f"(5 estados: {novas_5:,} linhas corrigidas)")

    print("\n" + "=" * 60)
    print("[CONCLUIDO] Todos os anos/tabelas corrigidos.")
    print("Agora rode novamente: py download_pam_ibge.py")
    print("(vai pular o download - todos os anos ja existem - e so reconsolidar)")
    print("=" * 60)

if __name__ == "__main__":
    main()
