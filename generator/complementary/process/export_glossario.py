"""
export_glossario.py — gera public/data/glossario.json, a parte do glossário que sai
dos dados (a aba "Glossário" do painel e a página glossario.html leem o mesmo arquivo).

O texto das definições, fórmulas e cautelas fica em public/js/glossario.js. Aqui sai o
que depende do que o painel publica e por isso não pode ser digitado à mão:
  fontes     uma linha por base: instituição, tabela ou recurso, período coberto e data
             do download, lidos dos próprios JSON de public/data e dos manifestos;
  culturas   permanentes, temporárias e os grupos Colheitadeiras e Tratores do pkg.json;
  pecuaria   categorias de rebanho e de produção do ppm.json;
  pevs       categorias de cada tipo da PEVS, com nível, unidade e período, e as notas;
  car        as ressalvas por camada ambiental e a nota da estrutura fundiária, do car.json;
  dominante  os grupos das densidades prontas e as categorias da cultura dominante, com as
             culturas e a decisão de cada uma (pam_grupos.json e generator/grupo_dominante.csv);
  receita    períodos, atividades, tipos e setores da Receita e da ANP, e as UFs onde o
             produtor pessoa física tem CNPJ (produtores_mun.json e contas_chave.json).
O arquivo é pequeno: a página separada não precisa baixar o pkg.json (17 MB).

Rode depois de qualquer export que mude os dados do painel. Nada aqui depende de rede.
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import IBGE2UF, MANIFEST_DIR, RAW_DIR, now_iso, write_public_json  # noqa: E402

PUBLIC_DATA = Path(__file__).resolve().parents[3] / "public" / "data"
GENERATOR = Path(__file__).resolve().parents[2]
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _json(nome: str) -> dict:
    p = PUBLIC_DATA / nome
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _mes_ano(ano: int, mes: int) -> str:
    return f"{MESES[mes - 1]}/{ano}"


def _baixado_em(manifesto: str) -> str | None:
    """Mês e ano do download, do manifesto do bruto ("set/2026")."""
    p = MANIFEST_DIR / f"{manifesto}.json"
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8")).get("extraction_date") or ""
    if len(data) < 7:
        return None
    return _mes_ano(int(data[:4]), int(data[5:7]))


def _baixado_em_arquivo(rel: str) -> str | None:
    """Mês e ano do download de PAM, PPM e PEVS. O pipeline principal
    (generator/download_*_ibge.py) não grava manifesto; o consolidado municipal é o
    último arquivo que ele escreve, e a data dele marca o fim da coleta."""
    p = RAW_DIR / rel
    if not p.exists():
        return None
    t = datetime.fromtimestamp(p.stat().st_mtime)
    return _mes_ano(t.year, t.month)


def _extremos(anos: list | None) -> list:
    """Primeiro e último ano: o front mostra o período só da categoria que não cobre a série."""
    return [anos[0], anos[-1]] if anos else []


def _periodo(anos: list) -> str:
    return f"{anos[0]}–{anos[-1]}" if anos else "—"


def fontes(pkg, ppm, pevs, econ, terra, maq, cred, perfil, prod=None, contas=None) -> list[dict]:
    prod, contas = prod or {}, contas or {}
    f = [
        {"aba": "Agrícola", "base": "Produção Agrícola Municipal (PAM)", "instituicao": "IBGE",
         "origem": "SIDRA 1612 (lavouras temporárias) e 1613 (lavouras permanentes)",
         "periodo": _periodo(pkg.get("anos")),
         "baixado_em": _baixado_em_arquivo("ibge/pam/PAM_municipios_completo.csv")},
        {"aba": "Pecuária", "base": "Pesquisa da Pecuária Municipal (PPM)", "instituicao": "IBGE",
         "origem": "SIDRA 3939 (efetivo dos rebanhos) e 74 (produção de origem animal)",
         "periodo": _periodo(ppm.get("anos")),
         "baixado_em": _baixado_em_arquivo("ibge/ppm/PPM_municipios_completo.csv")},
        {"aba": "Silvicultura", "base": "Produção da Extração Vegetal e da Silvicultura (PEVS)",
         "instituicao": "IBGE",
         "origem": "SIDRA 291 (silvicultura), 289 (extração vegetal) e 5930 (área plantada)",
         "periodo": _periodo(pevs.get("anos")) + "; área plantada desde 2013",
         "baixado_em": _baixado_em_arquivo("ibge/pevs/PEVS_municipios_completo.csv")},
        {"aba": "Economia", "base": "PIB dos Municípios", "instituicao": "IBGE",
         "origem": "SIDRA 5938 (PIB e valor adicionado) e base de dados do PIB dos Municípios "
                   "(per capita oficial)",
         "periodo": f"PIB {econ.get('ano_pib', '—')}; VAB por setor {econ.get('ano_vab', '—')}",
         "nota": f"população do per capita: {econ['ref_pop']}" if econ.get("ref_pop") else None,
         "baixado_em": _baixado_em("raw_demografia_pib")},
        {"aba": "Uso do Solo", "base": "MapBiomas: cobertura e uso da terra", "instituicao": "MapBiomas",
         "origem": f"estatísticas por município, Coleção {terra.get('colecao', '—')}",
         "periodo": str(terra.get("ano", "—")), "baixado_em": _baixado_em("raw_mapbiomas")},
        {"aba": "Tratores", "base": "Censo Agropecuário", "instituicao": "IBGE",
         "origem": "SIDRA 6870 (tratores por faixa de potência)", "periodo": str(maq.get("ano", "—")),
         "baixado_em": _baixado_em("raw_censo_agro")},
        {"aba": "Crédito", "base": "Matriz de Dados do Crédito Rural (SICOR)", "instituicao": "Banco Central",
         "origem": "custeio e investimento por município (CusteioMunicipioProduto e InvestMunicipioProduto)",
         "periodo": f"contratos emitidos em {cred.get('ano', '—')}",
         "baixado_em": _baixado_em("raw_credito_rural")},
        {"aba": "CAR", "base": "Cadastro Ambiental Rural (SICAR)", "instituicao": "Serviço Florestal Brasileiro",
         "origem": "imóveis e camadas ambientais das 27 UFs; na Bahia, também o CEFIR",
         "periodo": "situação na data do download", "baixado_em": _baixado_em("raw_car")},
        {"aba": "Perfil do município", "base": "Módulo fiscal e fração mínima de parcelamento",
         "instituicao": "INCRA", "origem": "Índices Básicos (Instrução Especial nº 5/2022)",
         "periodo": "em vigor desde 2022", "baixado_em": _baixado_em("raw_modulo_fiscal")},
        {"aba": "Perfil do município", "base": "Censo Agropecuário: estabelecimentos", "instituicao": "IBGE",
         "origem": "SIDRA 6754 (estabelecimentos e área por grupo de área)",
         "periodo": str((perfil.get("anos") or {}).get("censo", "—")),
         "baixado_em": _baixado_em("raw_censo_agro")},
        {"aba": "Mapas e listas", "base": "Malhas e divisão territorial", "instituicao": "IBGE",
         "origem": "API de malhas (UF, microrregião, município) e de localidades",
         "periodo": "divisão vigente", "baixado_em": _baixado_em("raw_ibge_geography")},
        {"aba": "Agrícola", "base": "Áreas Territoriais", "instituicao": "IBGE",
         "origem": "área de cada município, denominador da densidade (ha/km²)",
         "periodo": "2025", "baixado_em": _baixado_em("raw_ibge_areas")},
        {"aba": "Produtores", "base": "Dados Abertos CNPJ", "instituicao": "Receita Federal",
         "origem": "estabelecimentos ativos com CNAE principal das divisões 01 e 02, só contados por município",
         "periodo": f"base de {prod.get('periodo_rfb', '—')}"
                    + (f", aberturas até {_data_br(prod['data_ref'])}" if prod.get("data_ref") else ""),
         "baixado_em": _baixado_em("produtores_rurais")},
        {"aba": "Contas-chave", "base": "Dados Abertos CNPJ", "instituicao": "Receita Federal",
         "origem": "estabelecimentos ativos de pessoa jurídica empresarial, pelo CNAE principal",
         "periodo": f"base de {contas.get('periodo_rfb', '—')}", "baixado_em": _baixado_em("contas_chave")},
        {"aba": "Contas-chave", "base": "Painel Dinâmico de Produtores de Etanol", "instituicao": "ANP",
         "origem": "capacidade autorizada de etanol por planta (pb-da-etanol.zip)",
         "periodo": f"mês {contas.get('mes_anp', '—')}", "baixado_em": _baixado_em("raw_anp_etanol")},
    ]
    return [{k: v for k, v in x.items() if v is not None} for x in f]


def _data_br(iso: str) -> str:
    return "/".join(reversed(iso[:10].split("-")))


def _dominante(grupos: dict) -> dict:
    """Categorias da cultura dominante com as culturas de cada uma e a decisão anotada
    (generator/grupo_dominante.csv), mais os grupos das densidades prontas."""
    p = GENERATOR / "grupo_dominante.csv"
    cats: dict[str, dict] = {}
    if p.exists():
        with open(p, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                k = (r.get("categoria") or "").strip()
                if not k:
                    continue
                o = cats.setdefault(k, {"culturas": [], "notas": []})
                o["culturas"].append(r["cultura"])
                if (r.get("observacao") or "").strip():
                    o["notas"].append(r["observacao"].strip())
    cores = grupos.get("categorias") or {}
    ordem = list(cores) or list(cats)
    return {"anos": {"pam": grupos.get("ano_pam"), "pevs": grupos.get("ano_pevs")},
            "categorias": [{"k": k, "cor": cores.get(k), **cats.get(k, {"culturas": [], "notas": []})}
                           for k in ordem],
            "grupos": {k: {c: g.get(c) for c in ("rot", "def", "fonte", "culturas")}
                       for k, g in (grupos.get("grupos") or {}).items()}}


def _receita(prod: dict, contas: dict) -> dict:
    """Rótulos e períodos da Receita, e onde o produtor pessoa física tem CNPJ: a
    cobertura que muda tudo na leitura dos produtores."""
    pf: dict[str, int] = {}
    for cod, r in (prod.get("mun") or {}).items():
        uf = IBGE2UF.get(str(cod)[:2], str(cod)[:2])
        for k, (n, _) in r.items():
            if k.endswith("|PF"):
                pf[uf] = pf.get(uf, 0) + n
    return {"periodo_rfb": prod.get("periodo_rfb") or contas.get("periodo_rfb"),
            "corte_24m": prod.get("corte_24m"), "mes_anp": contas.get("mes_anp"),
            "atividades": prod.get("atividades", {}), "tipos": prod.get("tipos", {}),
            "setores": {k: s.get("rot") for k, s in (contas.get("setores") or {}).items()},
            "pf_ufs": dict(sorted(pf.items(), key=lambda x: -x[1]))}


def _car(r: dict) -> dict:
    """Ressalvas do CAR que valem para o município inteiro de uma UF: as notas por
    camada (medidas compostas da BA e de SE, RS, PE) e a nota da estrutura fundiária."""
    return {"notas": r.get("notas", {}),
            "estrutura": (r.get("estrutura") or {}).get("nota"),
            "area_omitida": r.get("area_omitida")}


def build_glossario() -> dict:
    pkg, ppm, pevs = _json("pkg.json"), _json("ppm.json"), _json("pevs.json")
    econ, terra, maq = _json("econ.json"), _json("mapbiomas_mun.json"), _json("maquinas.json")
    cred, perfil, car = _json("credito.json"), _json("perfil.json"), _json("car.json")
    grupos, prod, contas = _json("pam_grupos.json"), _json("produtores_mun.json"), _json("contas_chave.json")
    sep = pevs.get("sep", "||")
    pevs_tipos = {}
    for tipo, cats in (pevs.get("categorias_por_tipo") or {}).items():
        pevs_tipos[tipo] = [{"categoria": c,
                             "nivel": (pevs.get("nivel_categoria") or {}).get(f"{tipo}{sep}{c}"),
                             "unidade": (pevs.get("unidades") or {}).get(c),
                             "periodo": (pevs.get("periodo_categoria") or {}).get(f"{tipo}{sep}{c}")}
                            for c in cats]
    return {
        "gerado_em": now_iso(),
        "fontes": fontes(pkg, ppm, pevs, econ, terra, maq, cred, perfil, prod, contas),
        "culturas": {k: pkg.get(k, []) for k in ("permanentes", "temporarias", "colheitadeiras", "tratores")},
        "pecuaria": {"rebanho": ppm.get("rebanho_categorias", []),
                     "producao": ppm.get("producao_categorias", [])},
        "pevs": {"anos": _extremos(pevs.get("anos")),
                 "tipos": pevs_tipos, "notas": pevs.get("notas", {})},
        "car": _car(car.get("ressalvas") or {}),
        "dominante": _dominante(grupos),
        "receita": _receita(prod, contas),
    }


def main():
    obj = build_glossario()
    p = PUBLIC_DATA / "glossario.json"
    write_public_json(p, obj)   # allow_nan=False: NaN no arquivo derrubaria a aba no navegador
    print(f"  glossario.json: {len(obj['fontes'])} fontes · "
          f"{sum(len(v) for v in obj['culturas'].values())} entradas de cultura · "
          f"{sum(len(v) for v in obj['pevs']['tipos'].values())} categorias da PEVS · "
          f"{p.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
