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
Índices básicos do INCRA em vigor (IE nº 5/2022), uma linha por município: 5.569. Ficam
sem linha Fernando de Noronha e Boa Esperança do Norte, que o INCRA não lista. Fontes e
conferência em METHODOLOGY, "Fonte do módulo fiscal".

| Campo | Tipo | Descrição |
|---|---|---|
| cod_municipio | str(7) | Código IBGE, como o INCRA o publica |
| modulo_fiscal_ha | float | Módulo fiscal (ha), de 5 a 110. A área do imóvel dividida por ele dá o número de módulos fiscais: pequena propriedade até 4, média de 4 a 15, grande acima de 15 (Lei 8.629/1993) |
| fracao_minima_parcelamento_ha | float | Menor área (ha) em que um imóvel pode ser desmembrado; imóvel menor que ela é minifúndio |
| zona_tipica_modulo | str | Zona típica de módulo, de A1 a C2: a da região geográfica imediata |
| zona_pecuaria | int | Zona de pecuária, de 1 a 5 |
| data_referencia | str | `2022-08-01`, publicação da IE nº 5/2022 |
| fonte | str | INCRA — Índices Básicos (IE nº 5/2022; tabela de 2013) |
| observacao | str | Só no DF: a zona típica é a de 2013, porque o Anexo III não a informa |

## censo_agro_<tema>  (`municipality/`)
Colunas: `cod_municipio`, `ano_referencia`, `categoria` (o tema), `subcategoria`,
`variavel`, `valor`, `unidade`, `fonte_tabela_sidra`. Cada tema vem de uma tabela do
Censo Agropecuário 2017 e abre por uma classificação; `subcategoria` é a categoria dela,
sempre com a linha `Total`:

| Tema | Tabela | Classificação | Variáveis |
|---|---|---|---|
| area_groups | 6754 | Grupos de área total | estabelecimentos; área (ha) |
| family_farming | 6778 | Tipologia | estabelecimentos |
| land_condition | 6853 | Condição do produtor em relação às terras | estabelecimentos |
| machinery | 6870 | Potência dos tratores | estabelecimentos com tratores; tratores |
| irrigation | 6859 | Método utilizado para irrigação | estabelecimentos com irrigação; área irrigada (ha) |
| storage | 6866 | Tipo de unidade armazenadora | estabelecimentos com unidades armazenadoras; unidades; capacidade (t) |
| finance | 6895 | Agente financeiro responsável pelo financiamento | estabelecimentos que obtiveram financiamento |
| technical_assistance | 6780 | Origem da orientação técnica recebida | estabelecimentos |
| land_use | 6881 | Utilização das terras | estabelecimentos com área; área (ha) |
| activity | 6778 | Grupos de atividade econômica | estabelecimentos |

Não somar as subcategorias: o `Total` já é a soma, e há categorias que se sobrepõem. Na
Tipologia, o familiar se abre em Pronaf B, Pronaf V e não pronafiano, e o Pronamp é outro
recorte do Total; um estabelecimento conta em cada método de irrigação, agente financeiro,
origem da orientação técnica ou tipo de unidade armazenadora que tem. `valor` nulo é o "-"
do SIDRA (zero) ou o "X" (sigilo, comum nas áreas e na capacidade em municípios com poucos
estabelecimentos). `unidade` é a da variável: Unidades, Hectares ou Toneladas.

`censo_agro_municipio_summary`: `numero_estabelecimentos` e `area_estabelecimentos_ha` são a
linha Total da area_groups (no Brasil, 5.073.324 estabelecimentos e 351.289.816 ha); a área
fica nula onde o IBGE a suprime. `censo_agro_area_groups_harmonizado`: as 18 classes de área
somadas em 6 faixas (`config/area_groups.csv`; o "Produtor sem área" fica de fora), para as
duas variáveis. A faixa com classe nula só se reconstrói quando as classes do município
fecham com o Total, e aí todo nulo era zero; senão fica nula, e ela não é deduzida por
diferença do Total, o que desfaria o sigilo. Na contagem, todas as faixas fecham; na área,
14.310 das 33.378 ficam nulas.

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
`unidade_quantidade` é a do SIDRA para a `quantidade` (Toneladas, Metros cúbicos ou,
no pinheiro brasileiro em árvores abatidas, Mil árvores) e fica nula na área
plantada, que vem em `area_ha`.

`produto` traz o rótulo do SIDRA com a numeração do IBGE ("1.2 - Lenha") e **mistura
níveis**: subtotais ("1.3 - Madeira em tora", "1 - Alimentícios"), produtos e, na
silvicultura desde 2013, a abertura por espécie ("1.2.3 - Lenha de eucalipto"). Somar
todas as linhas conta a mesma produção duas ou três vezes. `grupo` só vem preenchido no
nível de produto (ver METHODOLOGY, "PEVS — grupos de produtos"): somar as linhas com
`grupo` preenchido dá o Total do IBGE, ano a ano. Grupos da silvicultura:
`carvao_vegetal`, `lenha`, `madeira_tora_papel_celulose`, `madeira_tora_outros_fins`,
`outros_produtos_silvicultura`; da extração vegetal: `extracao_madeireira`,
`extracao_nao_madeireira`; da área plantada: `eucalipto`, `pinus`, `outras_especies`.

## rural_profile_stage1 / stage2  (`municipality/`)
Perfil municipal agregado. Stage 1: módulo fiscal, SNCR, Censo, PEVS (sem cruzar
PAM/PPM). Stage 2: acrescenta CAR (cadastros, área união, sobreposição e estrutura
fundiária) e MapBiomas (agricultura/pastagem/silvicultura, ha).

Da PEVS entra só a silvicultura (tabela 291), no **último ano** da `pevs_municipio` e só
no **nível de produto**, as linhas com `grupo` (ver pevs_municipio): subtotais e espécies
repetiriam produção. O último ano, e não uma média, porque fecha com o Total do IBGE e
não mistura preços de anos diferentes; a série inteira fica na `pevs_municipio`. O corte
é cíclico: o município que colheu nos anos anteriores e não no de referência fica sem
silvicultura no perfil. O teste `test_perfil_real_fecha_com_o_total_do_ibge` refaz a
conta contra o consolidado.

| Campo | Tipo | Descrição |
|---|---|---|
| modulo_fiscal_ha | float | Módulo fiscal do município (ha), da `dim_modulo_fiscal`; `null` em Fernando de Noronha e Boa Esperança do Norte |
| mediana_modulos_fiscais_car | float | Stage 2. Mediana do número de módulos fiscais das inscrições do CAR (`car_estrutura_fundiaria`) |
| percentual_pequenos_imoveis_car, _medios_, _grandes_ | float | Stage 2. % das inscrições do CAR até 4 MF, de 4 a 15 e acima de 15; `null` sem inscrição no CAR |
| percentual_area_pequenos_imoveis_car, _medios_, _grandes_ | float | Stage 2. % da área das inscrições em cada classe, com a sobreposição entre cadastros |
| valor_producao_florestal | float | Valor da produção da silvicultura no ano, R$ mil nominais; em cada município e somado no Brasil, é o Total do IBGE. `0` quando a fonte informa zero (valor arredondado); `null` sem silvicultura no ano ou sem informação |
| produto_florestal_predominante | str | Produto de maior valor no ano, com o rótulo do SIDRA ("1.2 - Lenha", "2.3 - Resina"). É o `produto`, e não o `grupo`: o grupo só junta casca de acácia-negra, folha de eucalipto e resina, e o produto diz qual deles. No empate, o primeiro rótulo; `null` sem valor positivo |
| silvicultura_presente | bool | O município tem valor da silvicultura no ano (o zero conta) |
| ano_referencia_pevs | int | Ano da PEVS dos três campos acima, o mesmo em todos os municípios; avança quando um ano novo entra na `pevs_municipio` |

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

## car_estrutura_fundiaria  (`geospatial/`)
Estrutura fundiária pelo CAR, uma linha por município com inscrição
(`process_car_estrutura.py`; método em METHODOLOGY, "Estrutura fundiária pelo CAR"). Conta
as inscrições não canceladas no município principal. O número de módulos de cada uma é a
área geométrica dividida pelo módulo fiscal do município. Usa os nomes do
`sncr_municipio_summary`, mas o universo é outro (ver CAR_LIMITATIONS).

| Campo | Tipo | Descrição |
|---|---|---|
| quantidade_imoveis | int | Inscrições não canceladas |
| area_imoveis_ha | float | Soma das áreas geométricas, com a sobreposição entre cadastros |
| quantidade_sem_modulo | int | Inscrições sem classe: área geométrica zero ou município sem módulo fiscal |
| modulos_fiscais_mediana | float | Mediana do número de módulos fiscais |
| quantidade_ate_1_mf, _1_2_mf, _2_4_mf, _4_15_mf, _acima_15_mf | int | Inscrições por faixa; somadas a `quantidade_sem_modulo`, dão `quantidade_imoveis` |
| area_ate_4_mf_ha, area_4_15_mf_ha, area_acima_15_mf_ha | float | Área das inscrições em cada classe |
| percentual_imoveis_ate_4_mf, _4_15_mf, _acima_15_mf | float | % das inscrições com classe: pequena (até 4 MF), média (4 a 15) e grande (acima de 15) |
| percentual_area_ate_4_mf, _4_15_mf, _acima_15_mf | float | % da área das inscrições com classe |
| metodo | str | Como a classe foi calculada |

Onde nenhuma inscrição tem classe, as faixas e os percentuais ficam nulos, nunca zero.

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
