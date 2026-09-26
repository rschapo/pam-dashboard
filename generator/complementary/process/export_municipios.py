"""
export_municipios.py — gera public/data/municipios.json, a divisão territorial que
o dashboard usa para completar a lista de municípios da PAM.

O pkg.json só traz os municípios com lavoura (mun_info) e as microrregiões deles
(mic_info). Economia, uso do solo, tratores, crédito e CAR cobrem o país inteiro,
e o front soma estado e microrregião a partir dos municípios: sem os 31 que a PAM
não lista (Recife, Vitória, Barueri…), o PIB de PE saía 24,6% menor, e a
microrregião de Fernando de Noronha nem aparecia no mapa.

Formato, compacto porque o arquivo é baixado na abertura do painel:
  mun: {cod_ibge: [nome, uf, cod_microrregiao]}
  mic: {cod_microrregiao: [nome, uf, nome_mesorregiao]}
Boa Esperança do Norte (MT), instalado em 2025, depois do fim das microrregiões,
fica sem microrregião aqui; o pkg.json já a traz com uma.

Lê data/processed/dimensions/dim_municipio (process_geography.py). Nada aqui
depende de rede.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import PROCESSED_DIR, now_iso  # noqa: E402

PUBLIC_DATA = Path(__file__).resolve().parents[3] / "public" / "data"
DIM = PROCESSED_DIR / "dimensions"


def _cod_mic(v) -> str | None:
    """A dimensão guarda o código da microrregião como texto de float ("26017.0")."""
    if v is None or pd.isna(v) or str(v).strip() == "":
        return None
    return str(int(float(v)))


def _texto(v) -> str | None:
    return None if v is None or pd.isna(v) else str(v)


def build_municipios() -> dict:
    p = DIM / "dim_municipio.parquet"
    if not p.exists():
        raise SystemExit(f"{p.name} ausente em {p.parent}. Rode process_geography.py.")
    df = pd.read_parquet(p)

    mun, mic = {}, {}
    for r in df.itertuples(index=False):
        mid = _cod_mic(r.cod_microrregiao)
        mun[str(r.cod_municipio)] = [r.nome_municipio, r.uf, mid]
        if mid:
            mic.setdefault(mid, [_texto(r.nome_microrregiao), r.uf, _texto(r.nome_mesorregiao)])

    return {
        "fonte": "IBGE, divisão territorial (dim_municipio, API de Localidades)",
        "gerado_em": now_iso(),
        "mun": dict(sorted(mun.items())),
        "mic": dict(sorted(mic.items())),
    }


def main():
    obj = build_municipios()
    PUBLIC_DATA.mkdir(parents=True, exist_ok=True)
    p = PUBLIC_DATA / "municipios.json"
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    kb = p.stat().st_size / 1024
    print(f"  municipios.json: {len(obj['mun']):,} municípios · {len(obj['mic'])} microrregiões · {kb:.0f} KB")


if __name__ == "__main__":
    main()
