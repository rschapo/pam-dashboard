# METHODOLOGY — Métodos de coleta, tratamento e cálculo

## Convenções gerais

Código municipal como **texto de 7 dígitos** (`common.cod_mun7`), sem `zfill`, com
integridade `cod[:2] == cod_uf` validada. UF em duas letras. Área sempre em **hectares**.
Valores monetários na unidade original da fonte (PEVS/Censo: R$ mil nominais),
documentada em campo próprio. Datas em ISO `YYYY-MM-DD`. **Ausência = `null`, nunca
zero**; zero só quando a fonte informa zero (`common.clean_num` converte `-`, `..`,
`X` → `None`).

Armazenamento de tabelas: **Parquet** (analítico) + **CSV `;`/UTF-8** (conferência).
Geometrias em GeoParquet/GeoPackage.

## Downloads

Coletores SIDRA replicam o padrão validado dos geradores PAM/PPM/PEVS: descoberta de
variáveis/classificações por **metadados** (`v3/agregados/{t}/metadados`), consulta de
valores em `n6` filtrado por `n3` (**uma UF por vez**), pausa entre requisições, retry
com backoff, tratamento de `429`/`400`, salvamento progressivo e retomada. Fontes sem
API estável (SNCR, SICAR, MapBiomas) usam **adaptador local**: o operador baixa o bruto
para `data/raw/...` e o script inventaria, hasheia e valida.

## Correspondência geográfica

- `dim_municipio` é construída da malha oficial (localidades/`ibge_municipios_full.csv`),
  preservando micro/mesorregião e incluindo regiões imediata/intermediária.
- Junções por nome (ex.: MapBiomas e crédito rural, cujas fontes não trazem o código) usam
  **(nome normalizado, UF)** contra a dimensão, com tabela de exceções revisável —
  **nunca** só por nome. Não correspondidos vão para `interim/` e para o manifesto.
- Correspondência de códigos históricos→atuais: `dim_municipio_codigos_historicos.csv`
  (populável por `config/municipio_code_history.csv`; não inventamos correspondências).

## Módulo fiscal e classificação

`numero_modulos_fiscais = area_ha / modulo_fiscal_ha`, com casas decimais preservadas.
Duas classificações mantidas em paralelo (`_stats.py`):

- **Analítica**: `ate_1_mf`, `mais_1_ate_2_mf`, `mais_2_ate_4_mf`, `mais_4_ate_10_mf`,
  `mais_10_ate_15_mf`, `mais_15_ate_50_mf`, `mais_50_mf`.
- **Legal operacional**: `ate_4_mf`, `mais_4_ate_15_mf`, `mais_15_mf`.

Não se rotula automaticamente todo imóvel < 1 MF como "minifúndio" nem se emite
conclusão jurídica individual — a classificação é analítica.

### Fonte do módulo fiscal

Os índices em vigor são os da Instrução Especial INCRA nº 5/2022 (DOU de 01/08/2022). O
INCRA não os publica numa tabela única, então `process_modulo_fiscal.py` os monta de
três peças oficiais:

- **Módulo fiscal e zona de pecuária:** vêm da tabela de Índices Básicos de 2013 (PDF,
  com o código IBGE de cada município). A IE os manteve: nos 1.885 municípios da planilha
  e nos 814 do trecho do Anexo IV, o valor de 2022 é o de 2013.
- **Fração mínima de parcelamento (FMP):** é a da planilha da IE nos 1.885 municípios em
  que ela mudou; nos demais, a de 2013.
- **Zona típica de módulo:** é a da região geográfica imediata do município, no Anexo
  III. Cada região tem uma zona só (art. 4º, §4º). A planilha não basta: há município
  que mudou de zona sem mudar a FMP e por isso não está nela. O DF vem sem zona no Anexo
  III e fica com a de 2013 (A1), a única compatível com a FMP e o limite que o anexo dá.

O Anexo IV traz todos os índices por município, mas só a versão certificada do DOU o tem
inteiro; a página web para em "Butiá". O processamento compara o resultado com esse
trecho, de 814 municípios, campo a campo: não há divergência. A consulta online do INCRA
("Consultar Índices Básicos") tem CAPTCHA e não é usada.

Dois municípios ficam sem índice: Fernando de Noronha, distrito estadual que a tabela do
INCRA não lista, e Boa Esperança do Norte (MT), instalado em 2025, depois da tabela de
2013.

### Estrutura fundiária pelo CAR

O SNCR, que daria a estrutura fundiária oficial, é baixado à mão, por UF, e ainda não foi.
`process_car_estrutura.py` faz a mesma conta com as inscrições do CAR, que cobrem o país
(`car_estrutura_fundiaria`):

- **Inscrições:** entram todas as não canceladas, cada uma contada uma vez. Os cancelados
  ficam de fora, como nas camadas ambientais: são 135.261.
- **Município:** cada inscrição vai para o município principal, onde está a maior parte
  da sua área, como no `car_municipio_summary`. As 25 inscrições sem interseção com a
  malha ficam no município declarado; o resumo as descarta, por isso 3 municípios têm 1
  ou 2 inscrições a mais aqui.
- **Número de módulos:** é a área geométrica dividida pelo módulo fiscal do município.
  Não se usa a área declarada, como em todo o CAR.
- **Classes:** as mesmas do SNCR (`_stats.FAIXAS_MF_LEGAL`). A pequena propriedade abre
  em até 1, de 1 a 2 e de 2 a 4 MF.
- **Área por classe:** é a soma das áreas das inscrições, com a sobreposição entre
  cadastros. Diz como a área cadastrada se divide, não quanto do território cada classe
  ocupa.

Ficam 146 inscrições sem classe: com área geométrica zero ou em município sem módulo
fiscal. O SICAR traz o número de módulos de cada inscrição, calculado com a área
declarada e o módulo fiscal do município declarado. A classe dele é a mesma daqui em
99,7% das inscrições, de 98,9% (RR) a 99,9% (SC). No Brasil, das 8.326.008 inscrições,
93,6% têm até 4 MF, 4,7% de 4 a 15 e 1,7% mais de 15. Elas somam, respectivamente,
24,7%, 16,8% e 58,6% da área cadastrada.

## Faixas de área do Censo (harmonização)

`config/area_groups.csv` mapeia cada classe original do Censo às faixas harmonizadas
(`ate_10_ha` … `mais_1000_ha`). A harmonização **soma apenas classes compatíveis**
(limites coincidentes em 10/50/100/500/1000 ha), **mantém a classe original**, marca
"Produtor sem área" como incompatível e **não interpola** — se uma faixa não puder ser
reconstruída, fica registrada, não estimada.

## PEVS — grupos de produtos

As tabelas da PEVS (291 silvicultura, 289 extração vegetal, 5930 área plantada) trazem,
na mesma classificação, subtotais do IBGE, produtos e, na silvicultura desde 2013, a
abertura de cada produto por espécie. `config/forestry_groups.csv` classifica cada
categoria pelo **código interno do SIDRA** (o rótulo mudou em 2025, quando o IBGE
renumerou as espécies) como `produto`, `agregado`, `especie` ou `contagem`, e **só o
nível `produto` recebe grupo**. É o nível mais detalhado que existe na série inteira
(2004–2025): pôr o grupo na espécie deixaria 2004–2012 sem grupo, e pôr nos dois níveis
contaria a produção em dobro. Conferido no consolidado: cada subtotal é a soma dos seus
itens, cada produto é a soma das suas espécies, e a soma das linhas com grupo fecha com
o Total do IBGE em todos os anos (valor na produção, área na 5930). O teste
`test_consolidado_real_soma_por_grupo_fecha_com_o_total` refaz a conta quando o
consolidado está disponível.

Casos à parte: o pinheiro brasileiro em árvores abatidas é `contagem` (a mesma extração
da madeira em tora de pinheiro, em mil árvores e sem valor); a madeira em tora de
pinheiro é um produto próprio, fora de "7.3 - Madeira em tora". As espécies separadas
de "Outras espécies" em 2025 (acácia negra, cedro australiano, mogno africano e teca)
ficam no grupo `outras_especies`, para a série da área não quebrar. Um código que surgir
sem linha na config fica sem grupo e vai para os avisos do manifesto.

## Estatísticas fundiárias (SNCR)

Por município calculamos, sobre imóveis válidos, média/mediana/percentis (p10, p25,
p50, p75, p90), área máxima, **Gini** da área e **índice de concentração do top 10%**
(`_stats.gini`, `_stats.indice_top10`). Distribuições por **quantidade de imóveis** e
por **área ocupada** são calculadas **separadamente** (`percentual_imoveis_*` vs
`percentual_area_*`) — indicadores distintos, nunca confundidos. Gini validado contra
valores conhecidos (ex.: `[1,2,3,4,5] → 0,2667`) nos testes.

## CAR — geometrias (Etapa 2)

CRS de armazenamento **SIRGAS 2000 (EPSG:4674)**; área calculada em **SIRGAS 2000 /
Brazil Polyconic (EPSG:5880)** — nunca em coordenadas geográficas. Geometrias inválidas
corrigidas com `make_valid` e, em resíduo, `buffer(0)` (documentado); a original é
preservada. Comparamos área geométrica × declarada (flag de divergência > 20%) e
sinalizamos geometrias fora da UF e duplicidades. Inconsistências **não são
excluídas**: geram camada válida e camada de rejeições.

### Interseção municipal

Um imóvel pode cruzar limites: intersectamos a geometria com a malha municipal e
calculamos a área de cada parte. **Município principal** = maior área de interseção.
Mantemos a **distribuição** por município (`car_imovel_municipio_intersection`). Três
medidas distintas e documentadas: contagem principal (maior área), contagem territorial
(presença em todos os municípios) e área (distribuída pela interseção).

### Sobreposições

`area_bruta` (soma das áreas), `area_uniao` (dissolve/`union_all`), `area_sobreposta =
bruta − união`, `percentual_sobreposicao`. Bandas de alerta em `quality_rules.yaml`
(`sem_sobreposicao_relevante` … `mais_20_percentual`). Não se decide automaticamente
qual cadastro é o domínio válido. A soma das áreas do CAR **não** equivale à área
ocupada.

## MapBiomas e comparação CAR × MapBiomas

Estatística municipal por classe (área e % da área municipal), preservando a
classificação original e acrescentando `grupo_analitico` (`config/land_use_classes.csv`).
Coleção e versão sempre registradas; sem misturar anos/coleções. A comparação municipal
CAR × MapBiomas é apresentada como **diferença metodológica** (declaração × sensoriamento
remoto; datas, resolução e conceitos distintos), não como erro automático de uma fonte.
O piloto por imóvel (recorte de raster) só roda após relatório de viabilidade.

## Critérios de rejeição (resumo)

Área negativa, código municipal inexistente, município incompatível com a UF e registro
sem área vão para a base de rejeições (SNCR). No CAR, geometrias fora do Brasil/UF,
autointersecção irrecuperável e duplicidades são sinalizadas. Nada é descartado
silenciosamente; tudo fica no manifesto e no relatório de qualidade.
