"""
Shared IBGE lookups and geo-info builders reused by process_pam.py and
process_ppm.py — kept in one place so both generators stay in sync.
"""
import os
from pathlib import Path

_DATA = Path(__file__).resolve().parent.parent / "data"


def _raiz_bruta() -> Path:
    """Onde ficam os brutos — a mesma regra de complementary/common.py.

    O projeto vive numa pasta sincronizada, e os brutos moram fora dela: primeiro
    PAM_RAW_DIR no ambiente, depois o caminho escrito em data/raw_dir.txt; sem
    nenhum dos dois, data/raw como antes.
    """
    env = os.environ.get("PAM_RAW_DIR")
    if env:
        return Path(env).expanduser()
    ponteiro = _DATA / "raw_dir.txt"
    if ponteiro.exists():
        destino = Path(ponteiro.read_text(encoding="utf-8").strip()).expanduser()
        if destino.is_absolute():
            return destino
    return _DATA / "raw"


# Raiz dos brutos IBGE (PAM, PPM, PEVS) usada por todos os coletores e processadores.
RAW_IBGE = _raiz_bruta() / "ibge"

# Municípios instalados depois de 2017, quando o IBGE deixou de usar microrregiões:
# a API de localidades não lhes dá microrregião. Cada um fica na microrregião dos
# municípios de que foi desmembrado, para a microrregião continuar somando o mesmo
# que a UF. Acrescentar aqui quando o IBGE instalar município novo — os processadores
# avisam quando encontram município sem microrregião.
MICRO_MUNICIPIOS_NOVOS = {
    # Boa Esperança do Norte (MT), instalado em 2025, desmembrado de Sorriso e Nova
    # Ubiratã, ambos em Alto Teles Pires; a API o põe na região imediata de Sorriso.
    "5101837": "51006",
}


def completar_microrregiao(df, mun_col="Cod_Municipio", mic_col="Cod_Microrregiao",
                           copiar=("Microrregiao", "Cod_Mesorregiao", "Mesorregiao")):
    """Dá microrregião aos municípios de MICRO_MUNICIPIOS_NOVOS que vierem sem ela,
    copiando nome e mesorregião de outro município da mesma microrregião."""
    sem = df[mic_col].isna() | df[mic_col].astype(str).str.strip().isin(["", "nan"])
    for cod, mic in MICRO_MUNICIPIOS_NOVOS.items():
        alvo = sem & (df[mun_col].astype(str) == cod)
        if not alvo.any():
            continue
        df.loc[alvo, mic_col] = mic
        ref = df[(df[mic_col].astype(str) == mic) & ~alvo]
        for c in copiar:
            if c in df.columns and len(ref):
                df.loc[alvo, c] = ref[c].iloc[0]
    return df

IBGE2UF = {
    "11":"RO","12":"AC","13":"AM","14":"RR","15":"PA","16":"AP","17":"TO",
    "21":"MA","22":"PI","23":"CE","24":"RN","25":"PB","26":"PE","27":"AL","28":"SE","29":"BA",
    "31":"MG","32":"ES","33":"RJ","35":"SP",
    "41":"PR","42":"SC","43":"RS","50":"MS","51":"MT","52":"GO","53":"DF"
}

UF_NAMES = {
    "RO":"Rondônia","AC":"Acre","AM":"Amazonas","RR":"Roraima","PA":"Pará","AP":"Amapá","TO":"Tocantins",
    "MA":"Maranhão","PI":"Piauí","CE":"Ceará","RN":"Rio Grande do Norte","PB":"Paraíba",
    "PE":"Pernambuco","AL":"Alagoas","SE":"Sergipe","BA":"Bahia",
    "MG":"Minas Gerais","ES":"Espírito Santo","RJ":"Rio de Janeiro","SP":"São Paulo",
    "PR":"Paraná","SC":"Santa Catarina","RS":"Rio Grande do Sul",
    "MS":"Mato Grosso do Sul","MT":"Mato Grosso","GO":"Goiás","DF":"Distrito Federal"
}

UF_REGION = {
    "RO":"N","AC":"N","AM":"N","RR":"N","PA":"N","AP":"N","TO":"N",
    "MA":"NE","PI":"NE","CE":"NE","RN":"NE","PB":"NE","PE":"NE","AL":"NE","SE":"NE","BA":"NE",
    "MG":"SE","ES":"SE","RJ":"SE","SP":"SE",
    "PR":"S","SC":"S","RS":"S",
    "MS":"CO","MT":"CO","GO":"CO","DF":"CO"
}


def build_ufs_info(df, uf_col="UF"):
    return {uf: {"n": UF_NAMES.get(uf, uf), "r": UF_REGION.get(uf, "")}
            for uf in sorted(df[uf_col].unique())}


def build_mic_info(df, mic_col="Cod_Microrregiao", name_col="Microrregiao",
                    uf_col="UF", meso_col="Mesorregiao"):
    info = {}
    sub = df[[mic_col, name_col, uf_col, meso_col]].drop_duplicates()
    for _, row in sub.iterrows():
        info[str(row[mic_col])] = {
            "n": str(row[name_col]), "uf": str(row[uf_col]), "ms": str(row[meso_col])
        }
    return info


def build_mun_info(df, mun_name_col, mun_col="Cod_Municipio", uf_col="UF", mic_col="Cod_Microrregiao"):
    info = {}
    sub = df[[mun_name_col, mun_col, uf_col, mic_col]].drop_duplicates(mun_col)
    for _, row in sub.iterrows():
        info[str(row[mun_col])] = {
            "n": str(row[mun_name_col]), "uf": str(row[uf_col]), "mid": str(row[mic_col])
        }
    return info
