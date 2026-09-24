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

## Lacunas da própria base nacional (download de 2026-09)

As 135 camadas (27 UFs × 5) foram baixadas do SICAR e conferidas: todas legíveis,
fatias sem buraco, extração idêntica ao ZIP byte a byte, CRC íntegro. Ainda assim,
em alguns estados a base nacional traz só parte da camada — o arquivo está completo,
o conteúdo publicado é que é parcial. Baixar de novo não resolve.

| UF | camada | CAR (bruto) | referência | leitura |
|----|--------|-------------|------------|---------|
| BA | área consolidada | 948 feições, 0,44 Mi ha, 208 de 417 municípios | MapBiomas agro+pasto 17,5 Mi ha | praticamente ausente |
| BA | vegetação nativa | 9,0 Mi ha | MapBiomas natural 30,4 Mi ha | ~30%; MG e PI ficam em ~72% |
| BA | APP | 4,6% do território | PI 9,1% | cerca de metade dos vizinhos |
| PE | APP | 5,5% do território | PB 10,5%, AL 11,7% | cerca de metade; semiárido pode explicar parte |

**APP: confirmado pelo dissolve (2026-09-24).** A comparação de APP acima foi feita
pela soma bruta, e a camada de APP do SICAR traz o tema "APP Total" ao lado das
partes que o compõem (rios, nascentes, lagos) — na Bahia, 175 mil das 392 mil
feições. A soma bruta contava a mesma faixa duas ou mais vezes: dissolvida, a APP
cai para um quarto a metade do valor bruto em todos os estados.

| UF | APP dissolvida (% do território) | soma bruta |
|----|----------------------------------|------------|
| BA | 2,2% | 4,6% |
| PE | 1,6% | 5,5% |
| PB | 3,2% | 10,5% |
| AL | 2,8% | 11,7% |
| SE, RN, MA | 2,8%, 3,0%, 2,4% | — |

A Bahia fica dentro da faixa regional: a lacuna de APP era artefato da soma bruta.
Pernambuco segue em cerca de metade de Paraíba e Alagoas depois do dissolve, então
a diferença não é artefato — mas também não há referência independente para dizer
se é declaração incompleta ou característica da hidrografia. Fica marcado como
"abaixo dos vizinhos, sem confirmação".

**Cadastros cancelados.** O SICAR entrega também os cadastros que ele próprio
cancelou (`ind_status = CA`): na mediana, 6% da área registrada, e acima de 20%
em SP, PA, SE, RO, AC e MS. Desde 2026-09-23 a medição os exclui; as UFs medidas
antes disso foram arquivadas em `processed/geospatial/_arquivo/` e refeitas.

Nas oito UFs medidas pelos dois métodos (AC, AM, AP, MT, PA, RO, RR, TO), tirar
os cancelados reduz a área dissolvida em 8% a 10% por camada, somados os
estados — vegetação nativa de 151,2 para 136,7 Mi ha. Como a camada é
dissolvida, o cancelado só tira área onde nenhum cadastro ativo declara a mesma
coisa; o que sai é área que só uma declaração invalidada sustentava. O efeito é
maior no PA (vegetação nativa −19%, área consolidada −16%) e em RR (vegetação
nativa −18%, reserva legal −17%), e menor no MT (−2% a −3%).

### Bahia: o que o CEFIR explica (investigado em 2026-09)

A Bahia opera cadastro próprio, o CEFIR (Inema), e o SICAR da Bahia é o próprio CEFIR:
as contagens batem camada por camada (vegetação nativa 150.054 no SICAR contra 149.103
no CEFIR; reserva legal 1.123.045 contra 1.135.108). O CEFIR não esconde dado a mais.
O que muda é como ele registra o imóvel.

**Vegetação nativa — diferença de definição, não de cobertura.** No padrão nacional
as camadas se empilham: no MT, 99,3% da reserva legal também aparece como vegetação
nativa e 78,3% da APP também. Na Bahia, 0,0% e 3,8%: vegetação nativa, reserva legal
e APP são fatias disjuntas do imóvel. Só a camada "vegetação nativa" dá 9,0 Mi ha (30%
do natural do MapBiomas); somada à reserva legal, 17,4 Mi ha (57%); com a APP,
≈20 Mi ha (≈66%), em linha com MG e PI (~72%). Para a Bahia, a vegetação nativa
comparável é a união das três camadas — todas já baixadas do SICAR.

**Área consolidada — o CEFIR não tem essa camada para imóvel privado.** Só para
assentamentos (349 feições) e comunidades tradicionais (8), que é o que o SICAR repassa.
O que o CEFIR registra para o imóvel é a área de **atividades desenvolvidas**: 817.069
polígonos, 16,0 Mi ha declarados contra 17,5 Mi ha de agropecuária no MapBiomas (92%).
Não é o mesmo conceito legal — área consolidada é ocupação anterior a 22/07/2008 —,
mas é o equivalente produtivo, e deve ser rotulado assim.

Oito registros dessa camada têm área declarada absurda (até 96 milhões de ha, mais que
o estado) e respondem por 92% da soma declarada bruta; as geometrias deles têm de 0 a
26 ha. É erro de digitação no campo declarado. A medição geométrica não é afetada.

**APP — o CEFIR não acrescenta, e não faz falta.** O CEFIR tem menos APP que o SICAR
(213.596 contra 391.878 feições). A lacuna que parecia haver era da soma bruta:
dissolvida, a APP da Bahia fica na faixa dos vizinhos (ver acima). Pernambuco, que
não tem relação com o CEFIR, é o caso que continua abaixo.

Acesso: GeoServer público do Inema, WFS em
`http://geoserver.inema.ba.gov.br/geoserver/wfs` (HTTPS não responde), espaço
`Vetor_Recortes_Tematicos`, camadas `cefir_imovel_rural_*_inema`, com saída em
SHAPE-ZIP, JSON ou CSV e paginação por `startIndex`. Sem CAPTCHA. A camada de
limites traz nome do imóvel e do proprietário; só `ide_imovel` e `numero_car` são
necessários (o código IBGE do município está embutido no `numero_car`), e só esses
devem ser pedidos.

**Resultado da medição composta (2026-09-23, dissolve sem cancelados).**

| medida | CAR | MapBiomas | correlação por município | municípios > 100% |
|--------|-----|-----------|--------------------------|-------------------|
| vegetação nativa composta | 16,48 Mi ha | natural 30,42 Mi ha (54%) | r = 0,95 (416) | 0 |
| área de atividade | 13,70 Mi ha | agro+pasto 17,48 Mi ha (78%) | r = 0,93 (416) | 0 |

Os maiores municípios em área de atividade são o cinturão de grãos do oeste, com
valores próximos aos do MapBiomas: São Desidério 691 mil ha (MapBiomas 646 mil),
Formosa do Rio Preto 597 (565), Barreiras 333 (316), Luís Eduardo Magalhães 229 (236).

Os 54% de vegetação não são lacuna: o CAR cobre 59% do território baiano, contra 79%
do MT (ponderado por área). Divididos pela cobertura, a Bahia fica em 92% e o MT em
89%. O resto do território baiano — terra pública, fundos de pasto, áreas não
cadastradas — simplesmente não está no CAR.

Consequência para o painel: a Bahia entra com vegetação nativa composta e com área
de atividade no lugar da área consolidada, ambas rotuladas como equivalentes, a
partir de `car_ambiental_composta_BA`. A APP da Bahia entra normalmente; a de
Pernambuco entra com a marca "abaixo dos vizinhos, sem confirmação".

Método da varredura: feições por imóvel cadastrado em cada UF contra a mediana
nacional, marcando abaixo de um quinto; os casos marcados foram então confirmados
pela área. Contagem sozinha não basta, porque um estado de polígonos maiores tem
menos feições sem estar incompleto.

## Medição dissolvida: limite de precisão da geometria

Unir centenas de milhares de polígonos quase coincidentes esbarra no limite da
aritmética de ponto flutuante do GEOS ("non-noded intersection", "Ring edge
missing"), mesmo com toda a geometria válida. Na APP isso é comum, porque o tema
"APP Total" vem colado às partes que o compõem: na primeira rodada, a união exata
falhou em ao menos um município de 11 das 27 UFs (PA, TO, PI, CE, MG, SP, PR, SC,
RS, MT, GO), e a camada inteira dessas UFs ficou sem medir.

Nesses municípios, a medição refaz a operação com as coordenadas arredondadas a
1 mm de forma válida (`set_precision`); se ainda falhar, sobe a grade até 10 cm e,
por último, mede a área pelo Clipper, que trabalha em inteiros e não tem esse
limite. Onde a união exata funciona, nada muda. O resumo de cada camada informa
quantas operações precisaram de grade e quantos municípios foram pelo Clipper.

Validação cruzada na APP (2026-09-24):

| município | união exata | arredondada a 1 mm | Clipper |
|-----------|-------------|--------------------|---------|
| Água Azul do Norte (PA) | falha | 23.461,305 ha | 23.461,327 ha |
| Abaetetuba (PA) | falha | 13.431,964 ha | 13.431,969 ha |
| Porto Velho (RO) | 71.204,675 ha (−0,004%) | 71.207,685 ha | 71.207,719 ha |
| Ji-Paraná (RO) | 22.316,611 ha (−0,025%) | 22.321,729 ha (−0,002%) | 22.322,140 ha |

A arredondada e o Clipper concordam em até 0,002%. A união exata, quando não
falha, pode perder área sem avisar: nos dois municípios testados, 0,004% e 0,025%.
A APP de Ji-Paraná ocupa 3,2% do município; errar 0,025% dessa área muda o
percentual em 0,0008 ponto, duas ordens de grandeza abaixo da casa decimal que o
painel mostra.

## Validação contra o MapBiomas (2026-09-24)

`quality/validate_car_mapbiomas.py` compara, por UF, as camadas dissolvidas com o
MapBiomas 2024 (Coleção 10.1) e grava a tabela em `processed/state/car_mapbiomas_uf`.

- **Vegetação nativa × formação natural** — floresta, savana, campo e áreas úmidas.
  Floresta alagável e campo alagado são vegetação nativa, e sem elas a Amazônia e o
  Pantanal sairiam distorcidos. A vegetação fora do CAR (terra pública, área não
  cadastrada) não tem como aparecer nele, então a razão é dividida pela cobertura do
  CAR na UF antes de ser lida.
- **Área consolidada × agropecuária** — agricultura, pastagem, mosaico de usos e
  silvicultura. Lida direto, porque a agropecuária está quase toda em imóvel privado.
  Fica abaixo de 1 onde houve abertura depois de 22/07/2008, que pela lei não é
  consolidada.

A UF é sinalizada (negrito) se a razão lida sair de [0,5; 1,5] ou se a correlação por
município ficar abaixo de 0,7. Na mediana das UFs, a vegetação nativa fica em 73% do
esperado e a área consolidada em 86% da agropecuária, com correlações de 0,90 e 0,94.

| UF | cobertura do CAR | vegetação nativa ÷ natural | ÷ cobertura | r | consolidada ÷ agropecuária | r |
|----|------------------|----------------------------|-------------|---|----------------------------|---|
| AC | 75% | 60% | 80% | 0,84 | 88% | 0,98 |
| AL | 74% | 51% | 69% | 0,84 | 78% | 0,94 |
| AM | 55% | 36% | 64% | 0,74 | 102% | 0,92 |
| **AP** | 36% | 16% | 43% | 0,04 | 442% | 0,55 |
| BA | 59% | 54% | 92% | 0,95 | 55% | 0,95 |
| CE | 77% | 56% | 72% | 0,90 | 82% | 0,81 |
| DF | — | 67% | — | — | 124% | — |
| ES | 80% | 69% | 87% | 0,97 | 86% | 0,99 |
| GO | 88% | 78% | 89% | 0,97 | 89% | 0,99 |
| MA | 87% | 53% | 61% | 0,93 | 112% | 0,94 |
| MG | 87% | 64% | 73% | 0,96 | 85% | 0,97 |
| MS | 76% | 88% | 115% | 1,00 | 89% | 0,93 |
| MT | 82% | 69% | 83% | 0,89 | 91% | 0,96 |
| PA | 54% | 28% | 52% | 0,74 | 100% | 0,94 |
| PB | 75% | 58% | 78% | 0,89 | 71% | 0,86 |
| PE | 76% | 45% | 59% | 0,96 | 84% | 0,91 |
| PI | 73% | 60% | 82% | 0,95 | 82% | 0,93 |
| PR | 89% | 70% | 79% | 0,94 | 86% | 0,98 |
| RJ | 72% | 51% | 70% | 0,91 | 64% | 0,99 |
| RN | 80% | 78% | 98% | 0,90 | 56% | 0,85 |
| RO | 67% | 35% | 52% | 0,78 | 83% | 0,98 |
| **RR** | 33% | 17% | 53% | 0,83 | 119% | 0,52 |
| **RS** | 87% | 35% | 41% | 0,93 | 130% | 0,93 |
| **SC** | 84% | 53% | 63% | 0,70 | 102% | 0,84 |
| SE | 57% | 38% | 67% | 0,84 | 73% | 0,99 |
| SP | 88% | 71% | 80% | 0,90 | 68% | 0,97 |
| TO | 80% | 69% | 85% | 0,84 | 82% | 0,97 |

O DF não tem cobertura confiável — a base de imóveis é que está incompleta — nem
correlação, com um município só. As camadas ambientais dele vieram completas (16 mil
imóveis declaram área consolidada, 8 mil declaram APP) e entram no painel.

**RS — não é lacuna, é classificação.** A vegetação nativa fica em 41% do esperado e a
área consolidada passa a agropecuária em 30%. Somadas, as duas camadas fecham em 98%
do esperado, e o excedente da área consolidada sobre a agropecuária (+4,05 Mi ha)
acompanha, município a município, a fração de campo e savana nativos (r = 0,79). O
campo nativo usado para pecuária é declarado como área consolidada, e o MapBiomas o
classifica como formação campestre. O painel anota isso nas duas camadas do RS.

**SC** — só a correlação da vegetação nativa toca o limite (0,70); as duas camadas
somadas fecham em 93% do esperado. Sem ressalva.

**AP e RR** — 16 e 15 municípios, poucos para a correlação dizer muito, e o CAR cobre
um terço do território. A área consolidada do AP é 4,4 vezes a agropecuária do
MapBiomas, que no estado é mínima. Somadas, as camadas fecham em 58% (AP) e 69% (RR)
do esperado. Sem conclusão; ficam registradas.

Pernambuco, cuja APP ficou abaixo dos vizinhos, também tem a vegetação nativa na parte
baixa da faixa (59%, contra 78% na Paraíba e 69% em Alagoas). É coerente com
declaração mais incompleta no estado, mas não a confirma.

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
