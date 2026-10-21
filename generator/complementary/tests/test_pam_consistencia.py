"""PAM: a soma dos municípios (est_data do pkg.json) contra o total que o IBGE publica
por estado (PAM_estados.csv). Dado oficial não se corrige: onde o IBGE publicar uma
soma municipal diferente do total estadual, a divergência entra em EXCECOES, com a
fonte, e o teste passa a aceitá-la só ali."""
import json

import pandas as pd
import pytest

from common import RAW_DIR

PUBLIC_DATA = __import__("pathlib").Path(__file__).resolve().parents[3] / "public" / "data"

# (UF, cultura, ano) → motivo. Vazio em 21/10/2026: nenhuma divergência na série.
EXCECOES: dict[tuple[str, str, int], str] = {}


def test_soma_municipal_bate_com_o_total_estadual_publicado():
    est, pkg = RAW_DIR / "ibge" / "pam" / "PAM_estados.csv", PUBLIC_DATA / "pkg.json"
    if not est.exists() or not pkg.exists():
        pytest.skip("PAM_estados.csv ou pkg.json ausentes")
    e = pd.read_csv(est, sep=";", usecols=["UF", "Ano", "Cultura", "Area_Colhida_ha"])
    k = json.loads(pkg.read_text(encoding="utf-8"))
    idx = {a: i for i, a in enumerate(k["anos"])}
    fora = []
    for r in e.dropna(subset=["Area_Colhida_ha"]).itertuples(index=False):
        i = idx.get(int(r.Ano))
        if i is None:
            continue
        a = k["est_data"].get(r.UF, {}).get(r.Cultura, {}).get("a", [0] * len(idx))[i]
        if abs(a - r.Area_Colhida_ha) > 0.5 and (r.UF, r.Cultura, int(r.Ano)) not in EXCECOES:
            fora.append((r.UF, r.Cultura, int(r.Ano), r.Area_Colhida_ha, a))
    assert fora == [], f"{len(fora)} divergências não registradas; primeiras: {fora[:10]}"
