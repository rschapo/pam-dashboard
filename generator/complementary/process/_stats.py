"""
_stats.py — funções estatísticas fundiárias reutilizadas por SNCR e CAR.
Sem dependência de rede. Testadas em tests/test_geography.py::test_stats.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Faixas analíticas de módulos fiscais (briefing 6.6)
FAIXAS_MF_ANALITICA = [
    ("ate_1_mf", 0.0, 1.0),
    ("mais_1_ate_2_mf", 1.0, 2.0),
    ("mais_2_ate_4_mf", 2.0, 4.0),
    ("mais_4_ate_10_mf", 4.0, 10.0),
    ("mais_10_ate_15_mf", 10.0, 15.0),
    ("mais_15_ate_50_mf", 15.0, 50.0),
    ("mais_50_mf", 50.0, float("inf")),
]
# Classificação legal operacional (não emitir conclusão jurídica individual)
FAIXAS_MF_LEGAL = [
    ("ate_4_mf", 0.0, 4.0),
    ("mais_4_ate_15_mf", 4.0, 15.0),
    ("mais_15_mf", 15.0, float("inf")),
]


def faixa_mf(valor: float | None, faixas=FAIXAS_MF_ANALITICA) -> str | None:
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return None
    for nome, lo, hi in faixas:
        # (lo, hi]  — exceto a primeira faixa que inclui 0
        if (valor > lo or (lo == 0.0 and valor >= 0.0)) and valor <= hi:
            return nome
    return faixas[-1][0]


def gini(valores) -> float | None:
    """Coeficiente de Gini de um vetor de áreas/valores não negativos.
    Retorna None se n<2 ou soma zero. Fórmula da média das diferenças absolutas."""
    x = np.asarray([v for v in valores if v is not None and not (isinstance(v, float) and np.isnan(v))],
                   dtype=float)
    x = x[x >= 0]
    n = x.size
    if n < 2 or x.sum() == 0:
        return None
    xs = np.sort(x)
    idx = np.arange(1, n + 1)
    g = (2.0 * np.sum(idx * xs) / (n * xs.sum())) - (n + 1.0) / n
    return float(round(g, 4))


def indice_top10(valores) -> float | None:
    """Participação % da área detida pelos 10% maiores imóveis."""
    x = np.asarray([v for v in valores if v is not None and not (isinstance(v, float) and np.isnan(v))],
                   dtype=float)
    x = x[x >= 0]
    if x.size < 10 or x.sum() == 0:
        return None
    xs = np.sort(x)[::-1]
    k = max(1, int(np.ceil(0.10 * xs.size)))
    return float(round(100.0 * xs[:k].sum() / xs.sum(), 2))


def percentis(valores, ps=(10, 25, 50, 75, 90)) -> dict:
    x = np.asarray([v for v in valores if v is not None and not (isinstance(v, float) and np.isnan(v))],
                   dtype=float)
    if x.size == 0:
        return {p: None for p in ps}
    q = np.percentile(x, ps)
    return {p: float(round(v, 4)) for p, v in zip(ps, q)}


def resumo_area(areas: pd.Series) -> dict:
    """Estatísticas de distribuição de área para um município."""
    a = pd.to_numeric(areas, errors="coerce").dropna()
    pc = percentis(a.tolist())
    return {
        "area_total_cadastrada_ha": round(float(a.sum()), 4) if len(a) else None,
        "area_media_ha": round(float(a.mean()), 4) if len(a) else None,
        "area_mediana_ha": pc[50],
        "area_p10_ha": pc[10], "area_p25_ha": pc[25],
        "area_p75_ha": pc[75], "area_p90_ha": pc[90],
        "area_maxima_ha": round(float(a.max()), 4) if len(a) else None,
        "coeficiente_gini_area": gini(a.tolist()),
        "indice_concentracao_top_10": indice_top10(a.tolist()),
    }
