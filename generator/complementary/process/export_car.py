"""
export_car.py — gera o JSON do Cadastro Ambiental Rural para o dashboard.

Grava public/data/car.json com o resumo municipal do CAR: quantos imóveis rurais
estão cadastrados, o tamanho típico da propriedade, quanto do território está
declarado e quanto os cadastros se sobrepõem entre si. E, das camadas ambientais,
quanto de vegetação nativa, reserva legal, APP, área consolidada e uso restrito
foi declarado em cada município.

Um corte de qualidade, porque o dado bruto não se sustenta em todos os casos: a
área é omitida onde passa de 105% da área do município. Um imóvel que cruza
divisas é atribuído por inteiro a um município só, então municípios vizinhos de
grandes propriedades acumulam área que fisicamente não cabe neles. Vale para a
área declarada e para cada camada ambiental.

Omitir é deliberado: o campo ausente aparece como "sem dado" no painel, em vez
de um número que o usuário leria como medição. O município omitido sai também
do denominador dos percentuais ("pareado" nas razões), senão o estado somaria o
território dele sem a área correspondente.

As camadas ambientais vêm de process_car_dissolve.py, não das colunas de mesmo
nome em car_municipio_summary: aquelas são a soma bruta dos polígonos, que conta
duas vezes a área de cadastros sobrepostos e estoura o território. A Bahia e
Sergipe usam medidas compostas, porque lá o imóvel é declarado de outro jeito
(ver docs/CAR_LIMITATIONS.md).

A área típica do imóvel sai como média (área ÷ imóveis) e não como mediana: a
mediana municipal não se recompõe em estado nem em microrregião, e o painel
precisa do mesmo indicador nos três níveis.

Nada aqui depende de rede.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import PROCESSED_DIR, now_iso  # noqa: E402

PUBLIC_DATA = Path(__file__).resolve().parents[3] / "public" / "data"
GEO = PROCESSED_DIR / "geospatial"

COBERTURA_MAX = 1.05
METODO = "dissolve, sem cancelados"

# campo no JSON → camada dissolvida
CAMADAS = {
    "vn": "vegetacao_nativa",
    "rl": "reserva_legal",
    "app": "app",
    "ac": "area_consolidada",
    "ur": "uso_restrito",
}
ROTULOS = {
    "vn": "Vegetação nativa",
    "rl": "Reserva legal",
    "app": "APP",
    "ac": "Área consolidada",
    "ur": "Uso restrito",
}
# Onde a UF declara de outro jeito, a vegetação nativa comparável ao padrão
# nacional é a composta: na Bahia, porque o CEFIR registra vegetação nativa,
# reserva legal e APP como fatias separadas; em Sergipe, porque a maioria dos
# imóveis declara reserva legal sem declarar a vegetação nativa. Na Bahia, a área
# de atividade entra no lugar da consolidada, que o CEFIR não tem para imóvel
# privado.
COMPOSTAS = {"vn": "vegetacao_nativa_composta", "ac": "area_atividade"}
NOTA_COMPOSTA = {
    "BA": {
        "vn": "BA: vegetação nativa composta (nativa, reserva legal e APP, menos área "
              "degradada), porque o cadastro estadual registra as três em separado.",
        "ac": "BA: área de atividade declarada no cadastro estadual, no lugar da "
              "consolidada, que ele não tem para imóvel privado.",
    },
    "SE": {
        "vn": "SE: vegetação nativa composta (nativa, reserva legal e APP), porque a "
              "maioria dos imóveis declara reserva legal sem declarar a vegetação nativa.",
    },
}
# Ressalvas que a medição não resolve; o motivo de cada uma está em
# docs/CAR_LIMITATIONS.md. A APP de PE fica abaixo dos vizinhos mesmo dissolvida,
# sem referência que diga se é declaração incompleta ou hidrografia. No RS, o
# campo nativo pastejado é declarado como área consolidada: somadas, as duas
# camadas fecham com o MapBiomas, mas a divisão entre elas segue a declaração.
RESSALVAS = {
    "app": ["PE: abaixo dos vizinhos, sem confirmação."],
    "vn": ["RS: o campo nativo com pecuária é declarado como área consolidada, "
           "e não como vegetação nativa."],
    "ac": ["RS: inclui o campo nativo com pecuária, que o MapBiomas classifica "
           "como vegetação natural."],
}


def _num(v):
    if v is None:
        return None
    f = float(v)
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, 2) if f % 1 else int(f)


def camadas_ambientais(dim: pd.DataFrame) -> tuple[pd.DataFrame, dict, float]:
    """Área dissolvida (ha) por município e camada, só nas UFs em que foi medida.

    O dissolve só tem linha para município com alguma feição. Numa UF medida,
    município sem linha não declarou nada naquela camada e entra com zero —
    senão o estado perderia o território dele no denominador do percentual.
    """
    partes, substituidas, fora = [], {}, 0.0
    for p in sorted(GEO.glob("car_ambiental_dissolve_*.parquet")):
        uf = p.stem.rsplit("_", 1)[1]
        d = pd.read_parquet(p).set_index("cod_municipio")
        comp_p = GEO / f"car_ambiental_composta_{uf}.parquet"
        comp = pd.read_parquet(comp_p).set_index("cod_municipio") if comp_p.exists() else None
        metodos = set(d["metodo"]) | (set(comp["metodo"]) if comp is not None else set())
        if metodos != {METODO}:
            # O painel nunca compara estados medidos de jeitos diferentes.
            raise SystemExit(f"{p.name}: medido por {sorted(metodos)}, esperado '{METODO}'")
        cols = {}
        for campo, camada in CAMADAS.items():
            sub = COMPOSTAS.get(campo)
            if comp is not None and sub and f"{sub}_ha" in comp:
                cols[campo] = comp[f"{sub}_ha"]
                substituidas.setdefault(uf, []).append(campo)
            elif f"{camada}_ha" in d:
                cols[campo] = d[f"{camada}_ha"]
        if not cols:
            continue
        t = pd.DataFrame(cols)
        muns = pd.Index(dim.loc[dim["uf"] == uf, "cod_municipio"])
        # Código de município que não é da UF (erro no cod_imovel) não tem onde entrar.
        fora += float(t[~t.index.isin(muns)].sum().sum())
        partes.append(t.reindex(muns).fillna(0.0))
    if not partes:
        return pd.DataFrame(columns=list(CAMADAS)), substituidas, fora
    return pd.concat(partes), substituidas, fora


def build_car() -> dict:
    car = pd.read_parquet(GEO / "car_municipio_summary.parquet")
    dim = pd.read_parquet(PROCESSED_DIR / "dimensions" / "dim_municipio.parquet")
    area_mun = dim.set_index("cod_municipio")["area_municipal_ha"]
    d = car.set_index("cod_municipio")

    area_implausivel = d["area_geometrica_uniao_ha"] / area_mun.reindex(d.index) > COBERTURA_MAX

    amb, substituidas, ha_fora = camadas_ambientais(dim)
    amb_implausivel = amb.div(area_mun.reindex(amb.index), axis=0) > COBERTURA_MAX
    amb = amb.mask(amb_implausivel)

    # Território declarado, área média, sobreposição e os percentuais das camadas
    # são razões. O JSON carrega os componentes para que estado e microrregião
    # recomponham cada uma a partir das somas — somar percentuais daria o estado
    # como soma das taxas.
    mun: dict[str, dict] = {}
    for cod in d.index.union(amb.index):
        reg = {}
        if cod in d.index:
            r = d.loc[cod]
            reg = {"imov": _num(r["quantidade_cadastros"]),
                   "_asob": _num(r["area_sobreposta_ha"]),
                   "_abru": _num(r["area_geometrica_bruta_ha"])}
            if not area_implausivel[cod]:
                reg["area"] = _num(r["area_geometrica_uniao_ha"])
        if cod in amb.index:
            for campo, v in amb.loc[cod].items():
                if pd.notna(v):
                    reg[campo] = int(round(v))
        reg["_amun"] = _num(area_mun.get(cod))
        mun[str(cod)] = reg

    medidas = {c: sorted(amb.index.to_series().map(dim.set_index("cod_municipio")["uf"])
                         [amb[c].notna() | amb_implausivel[c]].unique())
               if c in amb else [] for c in CAMADAS}
    ufs = sorted(u for u in dim["uf"].dropna().unique())
    # O painel mostra a nota da camada escolhida; o texto sai daqui, junto das
    # decisões que o justificam.
    notas: dict[str, list[str]] = {}
    for uf, campos in substituidas.items():
        for c in campos:
            notas.setdefault(c, []).append(NOTA_COMPOSTA[uf][c])
    for c, textos in RESSALVAS.items():
        notas.setdefault(c, []).extend(textos)
    return {
        "fonte": "SICAR — Cadastro Ambiental Rural",
        "campos": {
            "imov": "Imóveis rurais cadastrados",
            "area": "Área declarada (ha)",
            "cob": "Território declarado (%)",
            "amed": "Área média do imóvel (ha)",
            "sobre": "Sobreposição entre cadastros (%)",
            **{c: f"{ROTULOS[c]} (ha)" for c in CAMADAS},
            **{f"{c}_p": f"{ROTULOS[c]} (% do território)" for c in CAMADAS},
        },
        "razoes": {
            "cob": {"num": "area", "den": "_amun", "fator": 100, "pareado": True},
            "amed": {"num": "area", "den": "imov", "fator": 1, "pareado": True},
            "sobre": {"num": "_asob", "den": "_abru", "fator": 100},
            **{f"{c}_p": {"num": c, "den": "_amun", "fator": 100, "pareado": True}
               for c in CAMADAS},
        },
        "ressalvas": {
            "area_omitida": int(area_implausivel.sum()),
            "metodo_camadas": METODO,
            "camadas_omitidas": {c: int(amb_implausivel[c].sum()) for c in CAMADAS if c in amb},
            "ufs_sem_camada": {c: [u for u in ufs if u not in medidas[c]] for c in CAMADAS},
            "substituidas": substituidas,
            "notas": notas,
            "ha_fora_da_uf": round(ha_fora),
        },
        "gerado_em": now_iso(),
        "mun": mun,
    }


def main():
    obj = build_car()
    PUBLIC_DATA.mkdir(parents=True, exist_ok=True)
    p = PUBLIC_DATA / "car.json"
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    r = obj["ressalvas"]
    print(f"  car.json: {len(obj['mun']):,} municípios · {p.stat().st_size / 1_048_576:.2f} MB")
    print(f"    área omitida em {r['area_omitida']} municípios (soma excede o território)")
    print(f"    camadas omitidas: " + ", ".join(f"{c} {n}" for c, n in r["camadas_omitidas"].items()))
    faltam = {c: u for c, u in r["ufs_sem_camada"].items() if u}
    if faltam:
        print("    camadas ainda sem medir: " + "; ".join(f"{c}: {', '.join(u)}" for c, u in faltam.items()))
    print(f"    substituídas pela medida composta: {r['substituidas']}")
    if r["ha_fora_da_uf"]:
        print(f"    {r['ha_fora_da_uf']:,} ha com código de município fora da UF, descartados")


if __name__ == "__main__":
    main()
