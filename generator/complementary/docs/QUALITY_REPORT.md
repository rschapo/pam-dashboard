# QUALITY_REPORT — Relatório de qualidade

Estado em 2026-07-28. Este relatório distingue o que foi **efetivamente processado**
do que tem **pipeline pronto aguardando o bruto oficial** (baixável só na sua máquina,
por causa da allowlist de rede — ver `INITIAL_ASSESSMENT.md`). Regenere com
`python quality/validate_outputs.py` após rodar os coletores.

## Cobertura por fonte

| Camada | Estado | Cobertura | Referência |
|---|---|---|---|
| `dim_municipio` | **Concluído** (offline) | 5.571 municípios, 27 UFs, 510 regiões imediatas | Malha base-mestra |
| Área municipal (ha) | Pendente | `null` p/ todos até carregar IBGE Áreas | — |
| `dim_modulo_fiscal` | **Concluído** (2026-09-26) | 5.569 municípios; sem índice só Fernando de Noronha e Boa Esperança do Norte | IE INCRA nº 5/2022 |
| Censo Agro 2017 (temático) | Pipeline pronto | aguarda SIDRA (tabelas validadas por metadados) | 2017 |
| `sncr_*` | Pipeline pronto | aguarda bruto por UF | — |
| `pevs_municipio` | Pipeline pronto | aguarda consolidado PEVS | 2004–2024 |
| CAR (Etapa 2) | Pipeline pronto (piloto por UF) | aguarda shapefiles por UF | — |
| MapBiomas | Pipeline pronto | aguarda estatística municipal | coleção/versão a registrar |

## Resultados de validação (o que já roda)

- `validate_geography`: **OK**. 5.571 municípios; 0 duplicados; 100% com 7 dígitos;
  integridade `cod[:2] == uf` **verdadeira**; 0 áreas iguais a zero (todas `null`,
  correto). Único aviso: área ausente (fonte IBGE Áreas não carregada).
- `validate_outputs`: **OK** — obrigatório (`dim_municipio`) presente; demais marcados
  como "pendente".
- Testes automatizados: **18 passam, 1 skip** (geopandas ausente neste ambiente).
  Cobrem normalização de código, nulos-nunca-zero, Gini (valores conhecidos), faixas
  de módulo fiscal, harmonização de faixas de área, agrupamento PEVS, hash anônimo e
  bandas de sobreposição.

## Dados faltantes, divergências, duplicidades e outliers

Ainda não mensuráveis para as camadas pendentes (sem bruto). Os mecanismos estão
implementados e serão preenchidos automaticamente na execução local:

- SNCR: `flag_area_zero/negativa/municipio_invalido/duplicidade/area_extrema`, base de
  rejeições e `sncr_rejeicoes.parquet`.
- CAR: geometrias corrigidas, fora da UF, divergência área declarada×geométrica (>20%),
  sobreposições (bandas), duplicidades.
- Censo: conferência com totais estaduais/nacionais (tolerância 1%), unidades
  preservadas, ausência ≠ zero.

## Municípios não correspondidos

`dim_municipio` inclui **todos** os municípios (universo completo), inclusive os sem
PAM/PPM (35 sem PAM, 25 sem PPM — marcados, não excluídos) e municípios recém-instalados
sem hierarquia micro/meso na DTB (ex.: Boa Esperança do Norte-MT; UF/região preenchidas
pelo código). Junções por nome (módulo fiscal) registram não correspondidos em `interim/`.

## Limitações

Ver `CAR_LIMITATIONS.md`. Em resumo: CAR é declaratório (sobreposições, ≠ título, ≠
SNCR, ≠ estabelecimento); área municipal depende de fonte IBGE ainda não carregada;
séries com anos de referência distintos; processamento nacional do CAR/MapBiomas exige
recursos e roda por UF.

## Recomendações

1. Rodar os coletores na sua máquina (rede aberta), começando por geografia+malha e
   módulo fiscal, depois Censo/PEVS, e o CAR por **UF piloto** antes do nacional.
2. Carregar a planilha IBGE Áreas Territoriais para preencher `area_municipal_ha`.
3. Validar as tabelas candidatas do Censo por metadados (`--dry-run`) antes do download.
4. Registrar coleção/versão do MapBiomas na coleta.
