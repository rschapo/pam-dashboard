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
