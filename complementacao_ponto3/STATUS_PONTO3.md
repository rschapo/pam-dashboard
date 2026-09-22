# STATUS — Complementação "Ponto 3" (PAM/IBGE) — atualizado 2026-08-11

**Conclusão: os itens A, B e C do briefing `BRIEFING_DADOS_PAM_IBGE.md` JÁ ESTÃO CONCLUÍDOS neste projeto.**
O briefing estava desatualizado (descrevia como pendente trabalho que já havia sido feito, ~2026-08-08). A confusão veio de a cópia em `C:\Users\schap\Claude\Projects\Dados IBGE PAM Culturas\` estar esvaziada (só um `.venv` quebrado); o projeto real e completo é este, no OneDrive.

## Onde está cada entrega (canônico)

**A — Malha municipal**
- `public/data/geo_mun.json` — Brasil inteiro, 5.570 municípios, schema `{cod_ibge (7 díg), uf}`. Cobre GO (246) e TO (139). ✅

**B — MapBiomas** (o briefing dava como pendente; está FEITO)
- Bruto: `data/raw/mapbiomas/mapbiomas_cobertura_municipios.xlsx` (77 MB) + `mapbiomas_pastagem_municipios.xlsx`
- Processado: `data/processed/municipality/mapbiomas_municipio.csv` (+ `.parquet`) — Coleção **10.1**, `data_download=2026-08-08`, schema `cod_municipio; ano; classe_id; classe_nome; grupo_analitico; area_ha; percentual_area_municipal; colecao; versao; data_download`
- Reconciliação: `data/processed/municipality/car_mapbiomas_comparacao.csv` ✅

**C — VAB/PIB**
- Processado: `data/processed/municipality/demografia_pib.csv` (5.571 mun) + `data/processed/state/demografia_pib.csv` (27 UF)
- Colunas: `cod_ibge; populacao; pib_total; impostos_liquidos; vab_agropecuaria; vab_industria; vab_servicos; pct_agro_no_pib; pib_per_capita; ano_ref; ano_ref_vab; fonte`
- **`ano_ref=2023` (PIB total) + `ano_ref_vab=2021` (VAB setorial)** — fonte `IBGE/SIDRA (tabelas 5938 e 6579)`. `pct_agro_no_pib` = vab_agropecuaria / VAB total.
- Brutos SIDRA: `data/raw/ibge/sidra_pibtotal_municipios_2023.json`, `sidra_vabsetorial_municipios_2021.json` (+ versões UF). ✅

## Por que 2023 no PIB mas 2021 no VAB
O IBGE publicou o **PIB total** dos municípios até 2023, mas a **abertura de VAB por setor** (agropecuária/indústria/serviços) só está disponível até **2021**. Não é limitação do pipeline — é disponibilidade do dado. Reconferido via API em 2026-08-11.

## Pipeline (tudo neste projeto)
`generator/complementary/` — `download/download_{demografia_pib,mapbiomas,ibge_geography,...}.py` + `process/process_{demografia_pib,mapbiomas,geo_municipal,...}.py` + `run_pipeline.py`. O `.venv` deste projeto (OneDrive) está ÍNTEGRO (`Scripts/python.exe`). Docs em `generator/complementary/docs/` (METHODOLOGY, DATA_DICTIONARY, INTEGRATION_PLAN, SOURCES, QUALITY_REPORT).

## Verificação independente (2026-08-11)
Nesta sessão, sem acesso inicial ao projeto real, reprocessei A e C do zero pelas APIs do IBGE (Malhas v3 e SIDRA 5938) e os resultados **bateram** com o canônico (GO 246 / TO 139; mesma lógica PIB 2023 / VAB 2021). Os scripts stdlib (sem geopandas/venv) ficaram em `scripts/build_geo_mun.py` e `scripts/build_pib.py` como fallback de rede.

## Pendências reais (não são dados — são integração)
O que o briefing chamava de "destrava no dashboard" ainda pode estar aberto: ligar o coroplético **municipal**, a **área mecanizável / reconciliação física** (MapBiomas) e o **VAB 2023** nas telas. Confirmar o estado do dashboard antes de seguir.
