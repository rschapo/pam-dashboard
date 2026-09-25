"""
download_censo_agro.py — Censo Agropecuário 2017 via SIDRA (roda na máquina do usuário).

Segue a REGRA do briefing (6.3): NÃO assume número de tabela — valida cada tabela
candidata (config/variables.yaml → censo_agro_2017) nos METADADOS antes de usar, e
descobre variáveis/classificações por nome (mesma técnica do download_pevs_ibge.py).

Baixa por UF (nível n6 filtrado por n3), com salvamento progressivo por tema/ano,
para data/raw/censo_agro/<tema>/. Retomável se interrompido.

Uso:
  python download_censo_agro.py                 # todos os temas
  python download_censo_agro.py --tema machinery irrigation
  python download_censo_agro.py --dry-run       # só valida tabelas nos metadados
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import (  # noqa: E402
    RAW_DIR, CONFIG_DIR, ESTADOS_COD, IBGE2UF, SidraClient,
    cod_mun7, clean_num, require_local_network, write_manifest, today_iso,
)

ANO_CENSO = 2017


def carregar_temas() -> dict:
    cfg = yaml.safe_load((CONFIG_DIR / "variables.yaml").read_text(encoding="utf-8"))
    return cfg["censo_agro_2017"]["temas"]


def validar_tabela(cli: SidraClient, tabela: int, temas_busca: list[str]) -> dict | None:
    """Confere nos metadados que a tabela existe e casa a classificação buscada.
    Retorna {'nome':..., 'classif':'c<id>'|None, 'ano_ok':bool} ou None se inválida."""
    try:
        meta = cli.metadados(tabela)
    except Exception as e:
        print(f"    [X] tabela {tabela}: metadados indisponíveis ({e})")
        return None
    nome = meta.get("nome", "")
    # classificação cujo nome casa com algum termo buscado
    classif = None
    classif_nome = ""
    for c in meta.get("classificacoes", []):
        cn = str(c.get("nome", "")).lower()
        if any(t.lower() in cn for t in temas_busca):
            classif = f"c{c['id']}"
            classif_nome = str(c.get("nome", ""))
            break
    periodos = [str(p.get("id")) for p in meta.get("periodos", [])] if "periodos" in meta else []
    ano_ok = (not periodos) or (str(ANO_CENSO) in periodos)
    print(f"    tabela {tabela}: {nome[:60]} | classif={classif} ({classif_nome}) | {ANO_CENSO} disponível={ano_ok}")
    return {"nome": nome, "classif": classif, "classif_nome": classif_nome,
            "meta": meta, "ano_ok": ano_ok}


def baixar_tema(cli: SidraClient, tema: str, cfg: dict, dry: bool):
    print(f"\n== Tema: {tema} — {cfg.get('descricao','')}")
    dst = RAW_DIR / "censo_agro" / tema
    dst.mkdir(parents=True, exist_ok=True)
    metricas = cfg.get("metricas", {"valor": ""})
    busca = cfg.get("classificacao_busca", [])

    tabela = None
    info = None
    for cand in cfg.get("tabelas_candidatas", []):
        info = validar_tabela(cli, cand, busca)
        if info and info["ano_ok"]:
            tabela = cand
            break
    if not tabela:
        print(f"  [X] nenhuma tabela candidata validada para '{tema}'. Ajuste variables.yaml.")
        return {"tema": tema, "tabela": None, "linhas": 0}
    if dry:
        return {"tema": tema, "tabela": tabela, "linhas": 0}

    variaveis = cli.descobrir_variaveis(info["meta"], metricas) if metricas else {}
    var_str = ",".join(variaveis.keys()) or "allxp"
    classif = info["classif"]
    classif_nome = info.get("classif_nome", "")
    # Nas tabelas do Censo a unidade é a da variável (Unidades, Hectares, %); as
    # categorias das classificações não trazem unidade.
    unid_var = {v.get("nome"): v.get("unidade") or "" for v in info["meta"].get("variaveis", [])}

    frames = []
    for cod_est in ESTADOS_COD:
        alvo = dst / f"{tema}_{tabela}_{IBGE2UF[str(cod_est).zfill(2)]}.csv"
        if alvo.exists():
            # Os brutos gravados até 25/09/2026 saíram com a unidade vazia: ela é
            # preenchida pela variável, sem baixar de novo e sem mexer no resto.
            d = pd.read_csv(alvo, sep=";", dtype=str, keep_default_na=False)
            vazia = d["unidade"] == ""
            if vazia.any():
                d.loc[vazia, "unidade"] = d.loc[vazia, "variavel"].map(unid_var).fillna("")
                d.to_csv(alvo, sep=";", index=False, encoding="utf-8")
            frames.append(d)
            continue
        dados = cli.valores_municipais(tabela, var_str, cod_est, ANO_CENSO, classif)
        if not dados or len(dados) < 2:
            pd.DataFrame().to_csv(alvo, index=False)
            continue
        cab = dados[0]
        def col(pred): return next((k for k, v in cab.items() if pred(v)), None)
        c_mc = col(lambda v: "Munic" in v and "digo" in v) or "D1C"
        c_vn = col(lambda v: v.strip() == "Variável") or col(lambda v: "Vari" in v and "Nome" in v) or "D2N"
        c_an = col(lambda v: "Ano" in v and "Nome" in v)
        # O cabeçalho do /values rotula a coluna com o NOME da classificação
        # ("Potência dos tratores"), não com a palavra "Nome" — casar pelo nome
        # vindo dos metadados, senão a subcategoria sai vazia e as categorias
        # da classificação viram linhas duplicadas indistinguíveis.
        c_cn = (col(lambda v: classif_nome and v.strip() == classif_nome)
                or col(lambda v: ("classifica" in v.lower()
                                  or any(b.lower() in v.lower() for b in busca))
                                 and "digo" not in v))
        # A coluna MN se chama só "Unidade de Medida", sem "Nome".
        c_un = col(lambda v: v.strip() == "Unidade de Medida") or "MN"
        linhas = []
        for row in dados[1:]:
            linhas.append({
                "cod_municipio": cod_mun7(row.get(c_mc)),
                "ano_referencia": ANO_CENSO,
                "categoria": tema,
                "subcategoria": row.get(c_cn, "") if c_cn else "",
                "variavel": row.get(c_vn, ""),
                "valor": clean_num(row.get("V")),
                "unidade": row.get(c_un, ""),
                "fonte_tabela_sidra": tabela,
            })
        d = pd.DataFrame(linhas)
        d.to_csv(alvo, sep=";", index=False, encoding="utf-8")
        frames.append(d)
        print(f"    {IBGE2UF[str(cod_est).zfill(2)]}: {len(d):,} linhas")
        time.sleep(cli.pause)

    total = pd.concat([f for f in frames if not f.empty], ignore_index=True) if frames else pd.DataFrame()
    return {"tema": tema, "tabela": tabela, "linhas": len(total)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tema", nargs="*", help="temas específicos (default: todos)")
    ap.add_argument("--dry-run", action="store_true", help="só valida tabelas nos metadados")
    args = ap.parse_args()
    require_local_network("Censo Agro/SIDRA")

    temas = carregar_temas()
    alvos = args.tema or list(temas.keys())
    cli = SidraClient()
    resumo = []
    for t in alvos:
        if t not in temas:
            print(f"  [!] tema desconhecido: {t}"); continue
        resumo.append(baixar_tema(cli, t, temas[t], args.dry_run))

    write_manifest("raw_censo_agro", source="IBGE — Censo Agropecuário 2017 (SIDRA)",
                   reference_date=f"{ANO_CENSO}-12-31",
                   row_count=sum(r["linhas"] for r in resumo),
                   warnings=[f"{r['tema']}: tabela {r['tabela']}" for r in resumo],
                   extra={"temas": resumo})
    print("\n[CENSO AGRO] concluído:", resumo)


if __name__ == "__main__":
    main()
