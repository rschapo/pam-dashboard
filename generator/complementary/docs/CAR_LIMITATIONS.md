# CAR_LIMITATIONS — Natureza e limites do Cadastro Ambiental Rural

O CAR é um registro **declaratório**, eletrônico e obrigatório, de âmbito nacional
(Lei nº 12.651/2012), voltado ao controle ambiental. Entender sua natureza é essencial
para não tirar conclusões indevidas dos números.

## O que o CAR NÃO é

- **Não é título de propriedade.** A inscrição no CAR **não** cria, reconhece nem prova
  domínio ou posse. É declaração para fins ambientais.
- **Não equivale ao imóvel econômico nem ao cadastro do SNCR.** CAR (ambiental, SFB),
  SNCR (cadastro rural, INCRA) e estabelecimento agropecuário (unidade de produção do
  Censo, IBGE) são universos **distintos**, com definições e recortes diferentes. Não
  se deve somá-los nem tratá-los como equivalentes.

## Sobreposição e duplicidade

Por ser declaratório, o CAR admite **sobreposição** de polígonos: dois cadastros podem
declarar a mesma área; um cadastro atualizado pode aparentar substituir outro. Logo:

- A **soma das áreas** do CAR de um município **não** equivale à área ocupada — pode
  superá-la. Por isso reportamos `area_bruta`, `area_uniao` (sem dupla contagem) e
  `area_sobreposta`, com bandas de alerta de sobreposição.
- Não decidimos automaticamente qual cadastro representa o domínio válido; apenas
  sinalizamos duplicidades e sobreposições para análise humana.

## Diferença entre inscrição e imóvel

Uma inscrição de CAR pode não corresponder a um único imóvel econômico, e um imóvel
pode cruzar limites municipais. Distinguimos **contagem principal** (município de maior
área), **contagem territorial** (presença em todos os municípios intersectados) e
**área distribuída** pela interseção — três medidas diferentes, sempre rotuladas.

## Área declarada × área geométrica

A área declarada pode divergir da área calculada a partir da geometria (erros de
digitalização, projeção, atualização). Mantemos as duas (`area_declarada_ha`,
`area_geometrica_ha`) e um indicador de divergência; **não** substituímos uma pela
outra. Áreas são calculadas em projeção métrica (EPSG:5880), nunca em graus.

## Camadas ambientais: a soma bruta não fecha com o território

`process_car_layers.py` soma, por município, a área de cada camada tal como declarada,
sem dissolver sobreposições e sem recortar pela malha municipal — o município vem do
código IBGE embutido em `cod_imovel`, então a geometria inteira do imóvel é contada no
município da inscrição. O resultado **não** pode ser lido como cobertura do território.

Medido no Acre, única UF com as cinco camadas presentes (2026-09):

| município | área consolidada | vegetação nativa | APP | soma |
|-----------|------------------|------------------|-----|------|
| Xapuri | 40,8% | **372,1%** | 8,4% | **421,3%** |
| Acrelândia | 97,9% | 51,1% | 10,1% | 159,1% |
| Sena Madureira | 16,6% | 135,5% | 6,2% | 158,4% |

Onze dos 22 municípios passam de 100% da área municipal. Para comparar, o MapBiomas
fecha em Acrelândia com 181.028 ha contra 181.161 ha de área municipal — diferença de
0,07%, porque parte de um raster sem sobreposição.

Antes de publicar qualquer indicador dessas camadas é preciso dissolver cada tema
(união geométrica, eliminando dupla contagem entre cadastros) e recortar pela malha
municipal. Enquanto isso não for feito, os campos `*_ha` e `percentual_*` servem para
inspeção da base, não para leitura como proporção do município.

## Diferenças entre UFs

O download é por UF e nem todas disponibilizam as mesmas camadas ambientais (área
consolidada, vegetação nativa, reserva legal, APP, uso restrito). Algumas UFs operam
sistemas estaduais próprios. `car_layer_availability.csv` e `CAR_SOURCE_MATRIX.md`
registram, por UF, o que existe e de onde veio. Não se presume uniformidade nacional.

## Privacidade e uso responsável

O objetivo **não** é cadastro nominal de proprietários. Nas bases tratadas: **sem**
CPF, CNPJ de titular, nome de pessoa física, endereço, telefone ou e-mail; **sem**
identificação de grupo familiar; **sem** reidentificação; **sem** prospecção
individualizada. Identificadores públicos de imóvel entram apenas como **hash** na
camada tratada; o bruto original é preservado à parte. Produtos finais são
predominantemente **agregados** por município, região e estado. Cuidado adicional com
uso comercial: dados ambientais declaratórios não devem embasar decisão individual.

## Data da base

O CAR é dinâmico (inscrições e retificações contínuas). Toda extração registra a data
de referência no manifesto; comparações entre CAR e outras fontes anotam o ano de cada
base.
