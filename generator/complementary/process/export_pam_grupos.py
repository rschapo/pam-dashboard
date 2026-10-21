"""
export_pam_grupos.py — gera public/data/pam_grupos.json: as áreas dos grupos de
culturas e a cultura dominante de cada município, no ÚLTIMO ano publicado do PAM (e
da PEVS, para a floresta plantada).

Alimenta, no domínio Agrícola do painel:
  - os atalhos "Densidades prontas" (cana, citros, café, floresta plantada, H&F, H&F
    sem citros, soja, milho, algodão, arroz, trigo, fumo, tratores e colheitadeiras;
    arroz, trigo e fumo pesam no Sul, sobretudo no RS): área do grupo ÷ área
    do município, sempre no último ano, e não no ano do seletor;
  - a "Cultura dominante": em cada município, a categoria de maior área entre as
    lavouras do PAM e a floresta plantada da PEVS. Pastagem não entra (o PAM não a mede).

As listas são versionadas ao lado do crop_groups.csv:
  generator/grupos_densidade.csv  grupo → culturas (cana, citros, café, H&F...)
  generator/grupo_dominante.csv   cultura → categoria da cultura dominante
  generator/crop_groups.csv       Colheitadeiras (COL) e Tratores (temporárias fora de COL)
O export ABORTA se uma parte do café (Arábica, Canephora; coluna `pai`) entrar num
grupo ou numa categoria: o Café Total já as contém. Também aborta se uma cultura do
PAM ficar sem categoria.

Município sem nenhuma linha no PAM do último ano fica sem "t" (sem lavoura publicada:
cinza no mapa, nunca zero); com PAM e sem a cultura, a área do grupo é zero. A PEVS
cobre todos os municípios, e quem não aparece nela não tem floresta plantada.

Nada aqui depende de rede.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import PROCESSED_DIR, RAW_DIR, now_iso, write_public_json  # noqa: E402

GENERATOR = Path(__file__).resolve().parents[2]
PUBLIC_DATA = Path(__file__).resolve().parents[3] / "public" / "data"
PAM_CSV = RAW_DIR / "ibge" / "pam" / "PAM_municipios_completo.csv"
PEVS = PROCESSED_DIR / "municipality" / "pevs_municipio.parquet"

# Cor fixa por categoria: a mesma no mapa interativo, no mapa estático e na tabela.
CORES_CATEGORIA = {
    "Cana": "#7CB342",
    "Grãos e oleaginosas": "#F2C12E",
    "Café": "#6D4C41",
    "Citros": "#FB8C00",
    "Frutas": "#D81B60",
    "Hortaliças e legumes": "#00897B",
    "Mandioca": "#8E24AA",
    "Cacau": "#BCAAA4",
    "Floresta plantada": "#1B5E20",
    "Outras lavouras": "#78909C",
}
FLORESTA = "Floresta plantada"
# Ordem dos atalhos no painel
ORDEM = ["cana", "citros", "cafe", "floresta", "hf", "hf_sem_citros", "soja", "milho",
         "algodao", "arroz", "trigo", "fumo", "tra", "col"]


def _csv(nome: str) -> list[dict]:
    with open(GENERATOR / nome, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def ler_tabelas(crop_groups=None, grupos=None, dominante=None):
    """Lê e confere as três tabelas. Devolve (grupos, categoria_da_cultura, filhas)."""
    crop_groups = crop_groups if crop_groups is not None else _csv("crop_groups.csv")
    grupos = grupos if grupos is not None else _csv("grupos_densidade.csv")
    dominante = dominante if dominante is not None else _csv("grupo_dominante.csv")

    culturas = {r["cultura"] for r in crop_groups}
    filhas = {r["cultura"]: r["pai"] for r in crop_groups if (r.get("pai") or "").strip()}

    out: dict[str, dict] = {}
    versoes = set()
    for r in grupos:
        c, g = r["cultura"], r["grupo"]
        if c in filhas:
            raise SystemExit(f"[ERRO] grupos_densidade.csv: '{c}' é parte de '{filhas[c]}' e não pode "
                             f"entrar no grupo '{g}' (contaria o café duas vezes)")
        if c not in culturas:
            raise SystemExit(f"[ERRO] grupos_densidade.csv: '{c}' (grupo '{g}') não é cultura do PAM")
        o = out.setdefault(g, {"rot": r["rotulo"], "fonte": "pam", "culturas": []})
        if c not in o["culturas"]:
            o["culturas"].append(c)
        versoes.add(r["versao"])
    versao = max(versoes) if versoes else "—"
    for o in out.values():
        n = len(o["culturas"])
        o["def"] = f"lista de culturas: definição {versao} · {n} cultura{'s' if n > 1 else ''}"

    col = [r["cultura"] for r in crop_groups if r.get("COL") == "1" and r["cultura"] not in filhas]
    tra = [r["cultura"] for r in crop_groups
           if r["tipo"] == "TEM" and r.get("COL") != "1" and r["cultura"] not in filhas]
    out["col"] = {"rot": "Colheitadeiras — grãos colhidos por colheitadeira", "fonte": "pam",
                  "culturas": sorted(col), "def": f"lista de culturas: crop_groups.csv (COL) · {len(col)} culturas"}
    out["tra"] = {"rot": "Tratores — temporárias não colhidas por colheitadeira", "fonte": "pam",
                  "culturas": sorted(tra),
                  "def": f"lista de culturas: crop_groups.csv (temporárias fora de COL) · {len(tra)} culturas"}
    out["floresta"] = {"rot": "Floresta plantada", "fonte": "pevs", "culturas": [],
                       "def": "área plantada de florestas, todas as espécies (PEVS)"}

    cat = {}
    for r in dominante:
        c, k = r["cultura"], (r.get("categoria") or "").strip()
        if c in filhas:
            if k:
                raise SystemExit(f"[ERRO] grupo_dominante.csv: '{c}' é parte de '{filhas[c]}' e não pode "
                                 f"ter categoria ('{k}')")
            continue
        if not k:
            raise SystemExit(f"[ERRO] grupo_dominante.csv: '{c}' sem categoria")
        if k not in CORES_CATEGORIA or k == FLORESTA:
            raise SystemExit(f"[ERRO] grupo_dominante.csv: categoria '{k}' sem cor em CORES_CATEGORIA")
        cat[c] = k
    sem = sorted(culturas - set(cat) - set(filhas))
    if sem:
        raise SystemExit(f"[ERRO] grupo_dominante.csv: culturas do PAM sem categoria: {', '.join(sem)}")
    return out, cat, filhas


def dominante(areas: dict[str, float]) -> str | None:
    """Categoria de maior área; empate desfeito pela ordem de CORES_CATEGORIA."""
    pos = [(v, -list(CORES_CATEGORIA).index(k), k) for k, v in areas.items() if v and v > 0]
    return max(pos)[2] if pos else None


def _int(v):
    return None if v is None or pd.isna(v) else int(round(float(v)))


def build_pam_grupos(pam: pd.DataFrame | None = None, pevs: pd.DataFrame | None = None,
                     tabelas=None) -> dict:
    grupos, cat, filhas = tabelas or ler_tabelas()

    if pam is None:
        if not PAM_CSV.exists():
            raise SystemExit(f"{PAM_CSV} ausente. Rode generator/download_pam_ibge.py.")
        pam = pd.read_csv(PAM_CSV, sep=";", dtype={"Cod_Municipio": str},
                          usecols=["Cod_Municipio", "Ano", "Cultura", "Area_Colhida_ha"])
    ano_pam = int(pam["Ano"].max())
    pam = pam[(pam["Ano"] == ano_pam) & ~pam["Cultura"].isin(filhas)].copy()
    pam["Cod_Municipio"] = pam["Cod_Municipio"].astype(str)
    fora = sorted(set(pam["Cultura"]) - set(cat))
    if fora:
        raise SystemExit(f"[ERRO] culturas do PAM {ano_pam} sem categoria: {', '.join(fora)}")

    if pevs is None:
        pevs = pd.read_parquet(PEVS, columns=["cod_municipio", "ano", "tipo_atividade", "area_ha"])
    flo = pevs[pevs["area_ha"].notna() & pevs["tipo_atividade"].astype(str).str.startswith("Área plantada")]
    ano_pevs = int(flo["ano"].max())
    # área plantada vem só por espécie (sem linha de total): a soma das espécies é o total
    flo = flo[flo["ano"] == ano_pevs].groupby("cod_municipio")["area_ha"].sum()

    # área por município e cultura; a linha sem número (NaN) não soma, mas o município
    # continua com PAM publicado
    por_cult = pam.groupby(["Cod_Municipio", "Cultura"])["Area_Colhida_ha"].sum(min_count=1)
    total = pam.groupby("Cod_Municipio")["Area_Colhida_ha"].sum()

    mun: dict[str, dict] = {}
    for cod, t in total.items():
        mun[cod] = {"t": _int(t), "g": {}, "c": {}}
    for (cod, cult), a in por_cult.items():
        if pd.isna(a) or a <= 0:
            continue
        reg = mun[cod]
        k = cat[cult]
        reg["c"][k] = reg["c"].get(k, 0) + a
        for g, o in grupos.items():
            if cult in o["culturas"]:
                reg["g"][g] = reg["g"].get(g, 0) + a
    for cod, a in flo.items():
        if a and a > 0:
            reg = mun.setdefault(str(cod), {"g": {}, "c": {}})
            reg["g"]["floresta"] = a
            reg["c"][FLORESTA] = a
    for reg in mun.values():
        reg["g"] = {k: _int(v) for k, v in reg["g"].items()}
        reg["c"] = {k: _int(v) for k, v in reg["c"].items()}
        d = dominante(reg["c"])
        if d:
            reg["d"] = d
        if not reg["g"]:
            del reg["g"]
        if not reg["c"]:
            del reg["c"]

    return {
        "fonte": "IBGE — PAM (SIDRA 1612 e 1613) e PEVS (SIDRA 5930, área plantada)",
        "gerado_em": now_iso(),
        "ano_pam": ano_pam,
        "ano_pevs": ano_pevs,
        "grupos": {k: grupos[k] for k in ORDEM if k in grupos},
        "categorias": CORES_CATEGORIA,
        "pastagem": "Pastagem não entra: o PAM não mede pastagem.",
        "mun": dict(sorted(mun.items())),
    }


def main():
    obj = build_pam_grupos()
    p = write_public_json(PUBLIC_DATA / "pam_grupos.json", obj)
    from collections import Counter
    dom = Counter(r.get("d") for r in obj["mun"].values())
    print(f"  pam_grupos.json: {len(obj['mun']):,} municípios · PAM {obj['ano_pam']} · PEVS {obj['ano_pevs']} · "
          f"{p.stat().st_size / 1_048_576:.2f} MB")
    print(f"    cultura dominante: {dict(dom.most_common())}")


if __name__ == "__main__":
    main()
