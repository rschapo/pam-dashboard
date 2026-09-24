# DATA_DICTIONARY — Dicionário das bases complementares

Chave de integração: **`cod_municipio`** (texto, 7 dígitos). Separador CSV `;`,
UTF-8, decimal `.`. Ausência = `null` (nunca zero). Cada tabela tem `.parquet`
(analítico) e, quando municipal, `.csv` (conferência).

## dim_municipio  (`data/processed/dimensions/`)
Dimensão territorial oficial (universo completo; municípios sem produção **incluídos**).

| Campo | Tipo | Descrição |
|---|---|---|
| cod_municipio | str(7) | Chave primária IBGE |
| nome_municipio | str | Nome |
| uf | str(2) | Sigla UF |
| nome_uf | str | Nome da UF |
| cod_regiao / nome_regiao | str/str | Grande região |
| cod_microrregiao / nome_microrregiao | str | Microrregião (compat. dashboard) |
| cod_mesorregiao / nome_mesorregiao | str | Mesorregião |
| cod_regiao_imediata / nome_regiao_imediata | str | Região geográfica imediata |
| cod_regiao_intermediaria / nome_regiao_intermediaria | str | Região geográfica intermediária |
| area_municipal_ha | float | Área territorial (ha); `null` se IBGE Áreas não carregada |
| ano_malha_referencia | int | Ano de referência da malha (rótulo declarado) |
| situacao_codigo | int | 0 = município instalado/ativo |
| flag_sem_producao_pam / _ppm | bool | Indicador de ausência na PAM/PPM interna (presença, não junção) |

Acompanha `dim_municipio_codigos_historicos.csv` (correspondência histórico→atual).

## dim_modulo_fiscal  (`dimensions/`)
`cod_municipio`, `modulo_fiscal_ha`, `fracao_minima_parcelamento_ha`,
`zona_tipica_modulo`, `zona_pecuaria`, `data_referencia`, `fonte`, `observacao`.

## censo_agro_<tema>  (`municipality/`)
Temas: area_groups, family_farming, land_condition, machinery, storage, irrigation,
finance, technical_assistance, land_use, activity. Colunas: `cod_municipio`,
`ano_referencia`, `categoria`, `subcategoria`, `variavel`, `valor`, `unidade`,
`fonte_tabela_sidra`. Harmonização em `censo_agro_area_groups_harmonizado`
(mantém a original; soma só compatíveis). Resumo em `censo_agro_municipio_summary`.

## sncr_imoveis_validos  (`municipality/`)
`id_imovel_hash` (SHA-256, **sem** dado nominal), `cod_municipio`, `uf`,
`area_total_ha`, `situacao_cadastral`, `data_referencia`, `fonte`,
`numero_modulos_fiscais`, `faixa_modulo_analitica`, `faixa_modulo_legal`,
`flag_area_zero`, `flag_area_negativa`, `flag_municipio_invalido`,
`flag_duplicidade`, `flag_area_extrema`. Rejeições em `interim/sncr/sncr_rejeicoes.parquet`.

## sncr_municipio_summary  (`municipality/`)
`cod_municipio`, contagens (total/válidos), estatísticas de área (média, mediana,
p10/p25/p75/p90, máxima, total), `coeficiente_gini_area`, `indice_concentracao_top_10`,
`modulos_fiscais_media/mediana`, contagens por faixa de MF, e — **distintos** —
`percentual_imoveis_*` vs `percentual_area_*` (até 4 / 4–15 / acima 15 MF).

## pevs_municipio  (`municipality/`)
`cod_municipio`, `ano`, `tipo_atividade` (Silvicultura / Extração vegetal / Área
plantada), `produto`, `quantidade`, `area_ha`, `valor_producao_mil_reais`,
`unidade_quantidade`, `grupo`, `fonte_tabela_sidra`. Categoria "Total" descartada.

## rural_profile_stage1 / stage2  (`municipality/`)
Perfil municipal agregado. Stage 1: módulo fiscal, SNCR, Censo, PEVS (sem cruzar
PAM/PPM). Stage 2: acrescenta CAR (cadastros, área união, sobreposição) e MapBiomas
(agricultura/pastagem/silvicultura, ha).

## car_imoveis_validos_<UF> / _intersection_<UF>  (`geospatial/`)
Geometrias tratadas (EPSG:4674), áreas (declarada × geométrica), flags e status
padronizado; interseção município×imóvel com `area_intersecao_ha`,
`percentual_area_imovel`, `municipio_principal`. Camadas: `car_layer_availability.csv`.

## car_municipio_summary  (`geospatial/`)
Contagens, `area_declarada_total_ha`, `area_geometrica_bruta_ha`,
`area_geometrica_uniao_ha`, `area_sobreposta_ha`, `percentual_sobreposicao`,
`nivel_sobreposicao`, estatísticas de área. Todo indicador informa a base usada
(bruta/declarada/geométrica/união/distribuída). As colunas de camada ambiental
(`area_consolidada_ha`, `vegetacao_nativa_ha`, `app_ha`...) são **soma bruta** dos
polígonos, que conta duas vezes a sobreposição; a medida sem dupla contagem está em
`car_ambiental_dissolve_<UF>`.

## car_ambiental_dissolve_<UF>  (`geospatial/`)
Área (ha) de cada camada ambiental por município, dissolvida — a área onde
cadastros se sobrepõem conta uma vez: `area_consolidada_ha`, `vegetacao_nativa_ha`,
`reserva_legal_ha`, `app_ha`, `uso_restrito_ha`, mais `uf` e `metodo`
("dissolve, sem cancelados"). O município vem do código IBGE no `cod_imovel`;
município sem feição na camada não tem linha (é zero). Gerado por
`process_car_dissolve.py`; limites e validação em `CAR_LIMITATIONS.md`.

## car_ambiental_composta_<UF>  (`geospatial/`, BA e SE)
Medidas comparáveis ao padrão nacional onde a UF declara de outro jeito. Bahia (o
CEFIR registra o imóvel em fatias separadas): `vegetacao_nativa_composta_ha`
(vegetação nativa ∪ reserva legal ∪ APP − áreas degradadas) e `area_atividade_ha`
(atividades desenvolvidas do CEFIR ∪ área consolidada do SICAR). Sergipe (a maioria
dos imóveis declara reserva legal sem vegetação nativa): `vegetacao_nativa_composta_ha`
(vegetação nativa ∪ reserva legal ∪ APP, sem desconto). Com `uf` e `metodo`.

## car_mapbiomas_uf  (`state/`)
Validação das camadas dissolvidas contra o MapBiomas, por UF
(`quality/validate_car_mapbiomas.py`): `cobertura_car`, e para vegetação nativa
(`vn_*`) e área consolidada (`ac_*`) a área do CAR, a referência, a razão, a razão
lida (a da vegetação dividida pela cobertura) e a correlação por município; `sinais`
lista o que ficou fora da faixa.

## mapbiomas_municipio  (`municipality/`)
`cod_municipio`, `ano`, `classe_id`, `classe_nome`, `grupo_analitico`, `area_ha`,
`percentual_area_municipal`, `colecao`, `versao`, `data_download`. Original preservada.
Comparação em `car_mapbiomas_comparacao` (metodológica).
