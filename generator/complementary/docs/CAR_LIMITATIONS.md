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

**Ressalva nas linhas de APP.** A comparação de APP acima foi feita pela soma bruta
das áreas, e a camada de APP do SICAR traz o tema "APP Total" ao lado das partes
que o compõem (rios, nascentes, lagos) — na Bahia, 175 mil das 392 mil feições.
A soma bruta conta a mesma faixa duas vezes, e se a proporção de "APP Total" muda
de um estado para outro, a comparação distorce. O dissolve elimina essa dupla
contagem; as duas linhas de APP só valem depois de confirmadas por ele.

**Cadastros cancelados.** O SICAR entrega também os cadastros que ele próprio
cancelou (`ind_status = CA`): na mediana, 6% da área registrada, e acima de 20%
em SP, PA, SE, RO, AC e MS. Desde 2026-09-23 a medição os exclui; as UFs medidas
antes disso foram arquivadas em `processed/geospatial/_arquivo/` e refeitas.

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

**APP — sem solução no CEFIR.** O CEFIR tem menos APP que o SICAR (213.596 contra
391.878 feições). A APP da Bahia segue parcial, assim como a de Pernambuco, que não
tem relação com o CEFIR.

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
partir de `car_ambiental_composta_BA`. A APP da Bahia e a de Pernambuco dependem da
confirmação pela medição dissolvida (ver ressalva acima).

Método da varredura: feições por imóvel cadastrado em cada UF contra a mediana
nacional, marcando abaixo de um quinto; os casos marcados foram então confirmados
pela área. Contagem sozinha não basta, porque um estado de polígonos maiores tem
menos feições sem estar incompleto.

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
