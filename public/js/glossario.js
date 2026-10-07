/* Glossário do painel: o que cada métrica mede, como é calculada e o que ela não
   permite concluir. Serve a aba "Glossário" do index.html, a página glossario.html
   e a dica "ⓘ" ao lado de cada seletor de métrica: o texto fica só aqui.

   O que depende dos dados vem de data/glossario.json (export_glossario.py): as
   fontes com período e data do download, as listas de culturas dos grupos, as
   categorias da pecuária e da PEVS e as ressalvas do CAR. Assim as listas não
   descolam do que o painel calcula. Sem o JSON, o texto aparece do mesmo jeito. */
'use strict';

const GLOSSARIO = (() => {

const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
// Busca sem acento e sem caixa: "producao" acha "Produção".
const norm = s => String(s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

// ─── Como ler o painel ───
const LER = [
  ['Abas de tema', 'Os botões no alto da barra lateral (Agrícola, Pecuária, Silvicultura e as demais) escolhem a base. Cada uma tem as suas métricas, explicadas abaixo.'],
  ['Mapa Brasil', 'Os estados coloridos pela métrica escolhida, com os indicadores do recorte no alto.'],
  ['Estado / Micro', 'As microrregiões do estado escolhido no filtro, no mapa e no gráfico.'],
  ['Municípios', 'Mapa, ranking e gráficos dos municípios do estado. Ao escolher um município aparecem a série dele e o perfil do município.'],
  ['Série Histórica', 'A evolução ano a ano. Só aparece nas bases com série (PAM, PPM e PEVS); as demais são o retrato de um ano.'],
  ['Rankings', 'Os maiores estados, microrregiões e culturas ou categorias na métrica escolhida.'],
  ['Concentração', 'Quanto da métrica se concentra em poucos municípios. Ver a seção Concentração, abaixo.'],
  ['Cores do mapa', 'Sete tons em escala logarítmica, do menor ao maior valor do mapa: cada tom cobre uma ordem de grandeza, e não faixas de mesmo tamanho. Zero e sem dado ficam no tom mais claro.'],
  ['Ano', 'O seletor segue a PAM. PPM e PEVS saem em outras datas: o ano que a base ainda não publicou mostra o último que ela tem, com o aviso "(último publicado)". Nas bases de um ano só, o seletor some.'],
  ['Estado e microrregião', 'Os totais somam os municípios. As razões (rendimento, per capita, percentuais, área média) são recalculadas sobre essas somas, e nunca são a média das razões municipais.'],
  ['— (traço)', 'Sem valor: a fonte não informa, o município não tem a atividade ou o dado foi omitido por qualidade. Nas razões, 0 é medida, e o traço quer dizer que falta base para calcular.'],
  ['mil, Mi, Gi', 'Milhares, milhões e bilhões. Valores em mil R$ estão em reais correntes do ano de referência, sem correção pela inflação.'],
];

// ─── Cuidados ao comparar ───
const CUIDADOS = [
  'Cinco áreas diferentes, que não se substituem: área colhida (PAM, conta cada safra), agricultura (MapBiomas, área ocupada vista por satélite), área declarada (CAR, imóveis), área dos estabelecimentos (Censo Agropecuário) e área financiada (crédito rural, por contrato).',
  'Valor da produção (PAM, PPM, PEVS), valor adicionado (PIB dos Municípios) e crédito rural medem coisas distintas, em anos distintos: não se somam nem se subtraem.',
  'Subtotais não se somam às partes: "Galináceos - total" já inclui as galinhas, o agregado da PEVS já inclui os produtos, e Permanentes, Temporárias, Colheitadeiras e Tratores são recortes que se sobrepõem.',
  'Imóvel do CAR, estabelecimento do Censo e contrato de crédito são unidades diferentes: um imóvel pode ter vários estabelecimentos, e um estabelecimento, vários contratos.',
  'Bases de um ano só (Economia, Uso do Solo, Tratores, Crédito, CAR) não acompanham o seletor de ano. O ano de cada uma está no rótulo da métrica e na tabela de fontes.',
];

// ─── Métricas por aba ───
// `id` é o value do seletor; `def` diz o que é, `calc` como sai quando não vem
// pronto da fonte, `nota` o que não se pode concluir. `aba` liga às fontes do JSON.
const CAMADAS_CAR = [
  ['vn', 'Vegetação nativa', 'Remanescente de vegetação nativa declarado nos imóveis.'],
  ['rl', 'Reserva legal', 'Parte do imóvel que o Código Florestal manda manter com vegetação nativa: de 20% a 80% dele, conforme o bioma e a região.'],
  ['app', 'APP', 'Área de preservação permanente: margens de rios, nascentes, encostas íngremes, topos de morro e as demais faixas protegidas pelo Código Florestal.'],
  ['ac', 'Área consolidada', 'Área com ocupação humana anterior a 22 de julho de 2008 (lavoura, pastagem, benfeitoria), que o Código Florestal permite manter em uso.'],
  ['ur', 'Uso restrito', 'Pantanais e planícies pantaneiras, e terrenos com inclinação entre 25° e 45°, onde o uso é limitado.'],
];
const CLASSES_MF = [
  ['pq', 'Pequenos', 'até 4 módulos fiscais'],
  ['md', 'Médios', 'de 4 a 15 módulos fiscais'],
  ['gr', 'Grandes', 'acima de 15 módulos fiscais'],
];
const NOTA_CLASSE = 'Conta inscrições não canceladas, e não propriedades; a área inclui a sobreposição entre cadastros.';

const ABAS = [
  { dom: 'agricola', nome: 'Agrícola', icone: '🌾', aba: 'Agrícola',
    intro: 'Lavouras temporárias e permanentes de cada município, por cultura e por ano.',
    metricas: [
      { id: 'p', nome: 'Produção', un: 't',
        def: 'Quantidade colhida no ano, somada entre as culturas do grupo, ou só a da cultura escolhida.',
        nota: 'Somar toneladas de culturas diferentes junta grão, cana e fruta num número só. Para comparar culturas entre si, use o valor ou a área.' },
      { id: 'a', nome: 'Área colhida', un: 'ha',
        def: 'Área de que se colheu a cultura no ano.',
        nota: 'Não é área física: a PAM conta cada safra, e o hectare com soja e milho de segunda safra entra duas vezes. A área ocupada está na aba Uso do Solo.' },
      { id: 'v', nome: 'Valor da produção', un: 'mil R$',
        def: 'Produção vezes o preço médio recebido pelo produtor, em reais correntes do ano.',
        nota: 'Sem correção pela inflação: comparar anos distantes exagera o crescimento.' },
      { id: 'r', nome: 'Rendimento', un: 'kg/ha',
        def: 'Produção dividida pela área colhida do recorte.', calc: 'Σ produção ÷ Σ área colhida × 1.000',
        nota: 'Razão das somas, não média dos rendimentos municipais. Com várias culturas no recorte, mistura produtividades muito diferentes: leia com uma cultura escolhida.' },
    ],
    extra: d => {
      const c = d?.culturas || {};
      const grupo = (titulo, desc, lista) => lista?.length ? `
        <h4>${titulo} <span class="gl-un">${lista.length} culturas</span></h4>
        <p>${desc}</p>${chips(lista)}` : '';
      return `
      <h4>Grupos de culturas</h4>
      <p data-busca="${norm('grupos culturas permanentes temporarias colheitadeiras tratores sobrepostos dupla contagem')}">
        <b>Permanentes</b> e <b>Temporárias</b> seguem a classificação do IBGE (tabelas 1613 e 1612).
        <b>Grãos / Colheitadeiras</b> e <b>Tratores</b> são a visão de máquina do painel: Colheitadeiras reúne
        as temporárias colhidas por colheitadeira, e Tratores, as demais temporárias. Os grupos se sobrepõem:
        somá-los conta a mesma cultura duas vezes. <b>Todas as Culturas</b> são as permanentes mais as temporárias.</p>
      ${d ? grupo('Permanentes', 'Lavouras que produzem por vários anos sem replantio.', c.permanentes)
          + grupo('Temporárias', 'Lavouras de ciclo curto, replantadas a cada safra.', c.temporarias)
          + grupo('Grãos / Colheitadeiras', 'Temporárias colhidas por colheitadeira.', c.colheitadeiras)
          + grupo('Tratores', 'Temporárias que não são colhidas por colheitadeira.', c.tratores)
          : semDados()}`;
    } },

  { dom: 'pecuaria', nome: 'Pecuária', icone: '🐄', aba: 'Pecuária',
    intro: 'Rebanhos e produção de origem animal de cada município, por ano.',
    metricas: [
      { id: 'q', nome: 'Quantidade', un: 'conforme a categoria',
        def: 'No Rebanho, o efetivo em 31 de dezembro, em cabeças. Na Produção animal, o que se produziu no ano: leite em mil litros, ovos em mil dúzias; mel, lã e casulos em kg.',
        nota: 'As categorias "total" já incluem as partes (Galináceos - total inclui as galinhas; Suíno - total, as matrizes): não as some.' },
      { id: 'v', nome: 'Valor da produção', un: 'mil R$',
        def: 'Valor da produção de origem animal, em reais correntes do ano.',
        nota: 'Só existe para a Produção animal: a PPM não dá valor ao rebanho.' },
    ],
    extra: d => `
      <p data-busca="${norm('revisao ano anterior ibge ppm')}">A cada divulgação o IBGE pode revisar o ano anterior; o painel usa a versão mais recente.</p>
      ${d ? `<h4>Rebanho</h4>${chips(d.pecuaria?.rebanho)}<h4>Produção animal</h4>${chips(d.pecuaria?.producao)}` : semDados()}` },

  { dom: 'silvicultura', nome: 'Silvicultura', icone: '🌲', aba: 'Silvicultura',
    intro: 'Produtos da silvicultura (florestas plantadas) e da extração vegetal (vegetação nativa), e a área plantada por espécie.',
    metricas: [
      { id: 'v', nome: 'Valor da produção', un: 'mil R$',
        def: 'Valor dos produtos no ano, em reais correntes.',
        nota: 'Sem correção pela inflação.' },
      { id: 'q', nome: 'Quantidade', un: 'conforme o produto',
        def: 'Quantidade produzida no ano, na unidade do produto: toneladas, metros cúbicos ou, no pinheiro-brasileiro abatido, milhares de árvores.',
        nota: 'Unidades diferentes não se somam: compare só produtos de mesma unidade.' },
      { id: 'a', nome: 'Área plantada', un: 'ha',
        def: 'Área com florestas plantadas em 31 de dezembro, por espécie. Publicada desde 2013.',
        nota: 'É estoque de área, não produção do ano.' },
    ],
    extra: d => `
      <h4>Níveis das categorias</h4>
      <ul class="gl-lista">
        <li data-busca="${norm('agregado subtotal')}"><b>Agregado</b>: subtotal do IBGE que soma produtos, como "1 - Alimentícios".</li>
        <li data-busca="${norm('produto item')}"><b>Produto</b>: o item publicado, como "Açaí (fruto)". Os rankings usam só este nível.</li>
        <li data-busca="${norm('especie abertura eucalipto pinus')}"><b>Espécie</b>: abertura de um produto da silvicultura por espécie, como o carvão de eucalipto, desde 2013.</li>
        <li data-busca="${norm('contagem arvores abatidas')}"><b>Contagem</b>: número de árvores abatidas, que não se soma a toneladas.</li>
      </ul>
      <p data-busca="${norm('niveis nao somar agregado produto especie')}">Não some níveis diferentes: o agregado já contém os produtos, e o produto, as espécies.
        A categoria que não cobre a série inteira mostra o período, como no seletor.</p>
      ${d ? Object.entries(d.pevs?.tipos || {}).map(([tipo, cats]) => `
        <details class="gl-det">
          <summary>${esc(tipo)} <span class="gl-un">${cats.length} categorias</span></summary>
          ${(d.pevs?.notas?.[tipo] || []).map(n => `<p class="gl-aviso" data-busca="${norm(tipo + ' ' + n)}">${esc(n)}</p>`).join('')}
          ${chipsPevs(cats, d.pevs)}
        </details>`).join('') : semDados()}` },

  { dom: 'economia', nome: 'Economia', icone: '📊', aba: 'Economia',
    intro: 'Produto Interno Bruto dos municípios e a parte da agropecuária no valor adicionado.',
    metricas: [
      { id: 'pib', nome: 'PIB total', un: 'mil R$',
        def: 'Produto Interno Bruto a preços correntes: o valor adicionado de todos os setores mais os impostos sobre produtos.',
        nota: 'Fica no município onde a produção acontece, não onde a renda é gasta: uma indústria, mina ou usina faz PIB alto em município pequeno.' },
      { id: 'agro', nome: 'VAB da agropecuária', un: 'mil R$',
        def: 'Valor adicionado bruto da agropecuária: o valor da produção menos os insumos consumidos nela.',
        nota: 'O VAB por setor sai depois do PIB total, e o ano de cada um está no rótulo da métrica. Não some ao valor da produção da PAM, que é medida bruta e de outra pesquisa.' },
      { id: 'pc', nome: 'PIB per capita', un: 'R$',
        def: 'PIB dividido pela população que o IBGE usa no per capita oficial do mesmo ano.', calc: 'PIB × 1.000 ÷ população',
        nota: 'Não usa a estimativa de população mais recente, para bater com o per capita oficial. Em estado e microrregião é o PIB somado sobre a população somada.' },
      { id: 'pct', nome: 'Agropecuária no VAB', un: '%',
        def: 'VAB da agropecuária dividido pelo VAB total, os dois do mesmo ano.', calc: 'VAB agropecuária ÷ VAB total × 100',
        nota: 'Não é a parte no PIB, que inclui os impostos e é de outro ano. Pode sair negativa onde o IBGE publica valor adicionado negativo.' },
    ] },

  { dom: 'terra', nome: 'Uso do Solo', icone: '🗺️', aba: 'Uso do Solo',
    intro: 'Cobertura e uso da terra mapeados por satélite pelo MapBiomas, em hectares, no ano mais recente da coleção.',
    metricas: [
      { id: 'natural', nome: 'Vegetação natural', un: 'ha',
        def: 'Formação florestal, savânica e campestre, área úmida e outras formações naturais.',
        nota: 'O campo nativo com pecuária do RS entra aqui; no CAR ele aparece como área consolidada.' },
      { id: 'agri', nome: 'Agricultura', un: 'ha',
        def: 'Lavouras temporárias e perenes.',
        nota: 'É área ocupada no ano, e não a área colhida da PAM, que conta cada safra.' },
      { id: 'past', nome: 'Pastagem', un: 'ha',
        def: 'Áreas de pastagem, na maior parte plantadas.',
        nota: 'A pastagem em campo nativo fica em Vegetação natural.' },
      { id: 'urban', nome: 'Urbano', un: 'ha',
        def: 'Área urbanizada: cidades, vilas e a infraestrutura delas.' },
      { id: 'agua', nome: 'Água', un: 'ha',
        def: 'Rios, lagos, reservatórios e demais corpos d\'água.',
        nota: 'As lagoas dos Patos e Mirim (RS) ficam fora de qualquer município no IBGE e não entram no total do estado.' },
      { id: 'outros', nome: 'Outros', un: 'ha',
        def: 'Área não vegetada (praias, dunas, mineração, afloramentos rochosos) e as classes sem grupo, como usina fotovoltaica e área não observada.' },
    ],
    extra: () => `
      <p data-busca="${norm('silvicultura mosaico de usos fora do seletor nao somam area do municipio')}">Silvicultura e mosaico de usos
        (agricultura e pastagem que o satélite não separa) não estão no seletor, e por isso as seis categorias não fecham a
        área do município. A silvicultura aparece no perfil do município.</p>` },

  { dom: 'maquinas', nome: 'Tratores', icone: '🚜', aba: 'Tratores',
    intro: 'Frota de tratores dos estabelecimentos agropecuários, recenseada pelo Censo Agropecuário.',
    metricas: [
      { id: 'trat', nome: 'Frota de tratores', un: 'tratores',
        def: 'Tratores existentes nos estabelecimentos na data de referência do Censo.',
        nota: 'Retrato de um ano, que só muda no próximo Censo. Mede o parque instalado, e não vendas nem idade da frota.' },
      { id: 'trat_p', nome: 'Tratores com menos de 100 cv', un: 'tratores',
        def: 'Parte da frota com potência abaixo de 100 cv.',
        nota: 'Em cerca de 600 municípios o IBGE não publica a frota por faixa, para não identificar estabelecimentos: ali as faixas ficam sem dado e não somam a frota.' },
      { id: 'trat_g', nome: 'Tratores de 100 cv ou mais', un: 'tratores',
        def: 'Parte da frota com 100 cv ou mais.',
        nota: 'Mesma ressalva de sigilo da faixa abaixo de 100 cv.' },
      { id: 'est', nome: 'Estabelecimentos com trator', un: 'estabelecimentos',
        def: 'Estabelecimentos que tinham ao menos um trator.',
        nota: 'Conta o estabelecimento uma vez, tenha ele um ou vários tratores: não é a frota.' },
    ] },

  { dom: 'credito', nome: 'Crédito', icone: '💰', aba: 'Crédito',
    intro: 'Crédito rural contratado no ano, por município, da Matriz de Dados do Crédito Rural do Banco Central.',
    metricas: [
      { id: 'total', nome: 'Crédito total', un: 'mil R$',
        def: 'Custeio mais investimento.', calc: 'custeio + investimento',
        nota: 'Não inclui comercialização nem industrialização. Conta o ano de emissão do contrato, e não o da safra.' },
      { id: 'cust', nome: 'Custeio', un: 'mil R$',
        def: 'Crédito para as despesas de um ciclo produtivo: insumos, tratos culturais e colheita.' },
      { id: 'inv', nome: 'Investimento', un: 'mil R$',
        def: 'Crédito para bens que duram vários ciclos: máquinas, benfeitorias, formação de lavoura permanente e animais.' },
      { id: 'area', nome: 'Área financiada', un: 'ha',
        def: 'Área informada nos contratos de custeio e de investimento.',
        nota: 'Não é área física: a mesma terra entra em cada contrato que a cita, como o custeio da safra e o da segunda safra.' },
    ] },

  { dom: 'car', nome: 'CAR', icone: '🌳', aba: 'CAR',
    intro: 'Imóveis rurais inscritos no Cadastro Ambiental Rural e o que eles declaram, por município. Tudo é autodeclarado e, na maior parte, ainda não analisado pelo órgão ambiental.',
    metricas: [
      { id: 'imov', nome: 'Imóveis rurais cadastrados', un: 'inscrições',
        def: 'Inscrições no CAR atribuídas ao município, inclusive as canceladas. O imóvel que cruza a divisa conta no município onde está a maior parte dele.',
        nota: 'Conta inscrições, e não propriedades nem proprietários.' },
      { id: 'area', nome: 'Área declarada', un: 'ha',
        def: 'Área da união dos polígonos dos imóveis do município: o que se sobrepõe conta uma vez.',
        nota: 'Omitida (—) onde passa de 105% da área do município, porque o imóvel que cruza a divisa entra inteiro num município só.' },
      { id: 'cob', nome: 'Território declarado', un: '%',
        def: 'Área declarada dividida pela área do município (IBGE).', calc: 'área declarada ÷ área do município × 100',
        nota: 'Abaixo de 100% não quer dizer que falte cadastro: cidades, estradas, água e áreas públicas não se inscrevem como imóvel rural.' },
      { id: 'amed', nome: 'Área média do imóvel', un: 'ha',
        def: 'Área declarada dividida pelo número de imóveis.', calc: 'área declarada ÷ imóveis',
        nota: 'Média, e não mediana: poucos imóveis grandes a puxam para cima. A mediana não se recompõe em estado e microrregião, e por isso fica de fora.' },
      { id: 'sobre', nome: 'Sobreposição entre cadastros', un: '%',
        def: 'Parte da área somada dos polígonos que se repete em mais de um cadastro.', calc: '(soma das áreas − área da união) ÷ soma das áreas × 100',
        nota: 'Sobreposição alta indica cadastros em conflito ou duplicados.' },
      ...CAMADAS_CAR.map(([id, nome, def]) => ({ id, nome, un: 'ha', def,
        nota: 'Área dissolvida da camada (a sobreposição conta uma vez), sem os cadastros cancelados.' })),
      ...CAMADAS_CAR.map(([id, nome]) => ({ id: id + '_p', nome: nome + ' (% do território)', un: '%',
        def: `Área da camada "${nome}" dividida pela área do município.`, calc: 'camada ÷ área do município × 100' })),
      ...CLASSES_MF.map(([id, nome, faixa]) => ({ id: id + '_n', nome: `${nome} (% dos imóveis)`, un: '%',
        def: `Parte dos imóveis classificados que tem ${faixa}.`, calc: 'módulos fiscais = área do imóvel ÷ módulo fiscal do município',
        nota: NOTA_CLASSE })),
      ...CLASSES_MF.map(([id, nome, faixa]) => ({ id: id + '_a', nome: `${nome} (% da área)`, un: '%',
        def: `Parte da área dos imóveis classificados que está em imóveis com ${faixa}.`,
        nota: NOTA_CLASSE })),
    ],
    extra: d => {
      const notas = d?.car?.notas || {};
      const nomes = Object.fromEntries(CAMADAS_CAR.map(([id, nome]) => [id, nome]));
      const linhas = Object.entries(notas).flatMap(([c, ns]) =>
        ns.map(n => `<li data-busca="${norm((nomes[c] || c) + ' ' + n)}"><b>${esc(nomes[c] || c)}</b>: ${esc(n)}</li>`));
      const omitida = d?.car?.area_omitida;
      return `
      ${omitida ? `<p data-busca="${norm('area declarada omitida 105% municipios sem dado')}">A área declarada fica
        sem dado em ${omitida.toLocaleString('pt-BR')} municípios, onde passaria de 105% da área do município.</p>` : ''}
      <h4>Estrutura fundiária</h4>
      <p data-busca="${norm('estrutura fundiaria modulo fiscal lei 8629 pequena media grande propriedade')}">As faixas seguem a
        Lei 8.629/1993: pequena propriedade até 4 módulos fiscais, média de 4 a 15 e grande acima de 15. O número de
        módulos de cada imóvel é a área dele dividida pelo módulo fiscal do município, fixado pelo INCRA.
        ${d?.car?.estrutura ? esc(d.car.estrutura) : ''}</p>
      ${linhas.length ? `<h4>Ressalvas por camada</h4><ul class="gl-lista">${linhas.join('')}</ul>` : ''}`;
    } },
];

// ─── Concentração ───
const CONCENTRACAO = {
  intro: 'Mede quanto da métrica escolhida se concentra em poucos municípios, dentro do recorte (Brasil, estado ou microrregião). Usa só os municípios com valor acima de zero, e não se aplica a razões como rendimento, per capita e percentuais, porque nelas não há um total a repartir.',
  itens: [
    { id: 'hhi', nome: 'HHI municipal', un: '0 a 10.000',
      def: 'Índice Herfindahl-Hirschman: soma dos quadrados das participações dos municípios.', calc: 'Σ (participação em %)²',
      nota: 'Acima de 2.500 é concentração alta. Cai quando há muitos municípios, mesmo que poucos dominem: leia junto com o Top 10.' },
    { id: 'gini', nome: 'Gini', un: '0 a 1',
      def: 'Desigualdade entre os municípios com valor: 0 é todos iguais; perto de 1, quase tudo num só.',
      nota: 'Mede desigualdade, e não tamanho: recortes de porte muito diferente podem ter o mesmo Gini.' },
    { id: 'top', nome: 'Top 10 e Top 5', un: '%',
      def: 'Parte do total que está nos 10 e nos 5 maiores municípios.' },
    { id: 'p50', nome: 'Para 50% e para 80% do total', un: 'municípios',
      def: 'Quantos municípios, do maior para o menor, bastam para somar metade e 80% do total.' },
    { id: 'n', nome: 'Municípios com valor', un: 'municípios',
      def: 'Municípios do recorte com valor acima de zero: a base de todos os cálculos acima.' },
    { id: 'pareto', nome: 'Curva de Pareto', un: '%',
      def: 'Participação acumulada dos municípios, do maior para o menor.',
      nota: 'Os cortes de 50% e 80% são de leitura, e não limiares estatísticos.' },
  ],
};

// ─── Perfil do município ───
const PERFIL = {
  intro: 'Aparece na visão Municípios ao escolher um município, em qualquer aba, e junta o que as bases complementares dizem dele.',
  itens: [
    { id: 'mf', nome: 'Módulo fiscal', un: 'ha',
      def: 'Unidade de área fixada pelo INCRA para cada município, conforme a exploração predominante. Vai de 5 a 110 ha.',
      nota: 'Serve para classificar os imóveis por tamanho; não é a área mínima de um imóvel.' },
    { id: 'fmp', nome: 'Fração mínima de parcelamento', un: 'ha',
      def: 'Menor área em que um imóvel rural pode ser desmembrado no município, também fixada pelo INCRA.' },
    { id: 'amun', nome: 'Área do município', un: 'ha',
      def: 'Área territorial oficial do IBGE, a mesma que serve de base aos percentuais do CAR.' },
    { id: 'car', nome: 'CAR e estrutura fundiária', un: '',
      def: 'Imóveis cadastrados, sobreposição e as barras de % dos imóveis e % da área em pequenos, médios e grandes, como na aba CAR.' },
    { id: 'est', nome: 'Estabelecimentos', un: 'Censo Agropecuário',
      def: 'Unidades de produção agropecuária recenseadas no município, cada uma sob uma única administração, e a área delas.',
      nota: 'Estabelecimento não é imóvel: um imóvel do CAR pode abrigar vários estabelecimentos, e um estabelecimento pode ocupar vários imóveis.' },
    { id: 'uso', nome: 'Uso do solo', un: 'MapBiomas',
      def: 'Agricultura, pastagem e silvicultura, em hectares, como na aba Uso do Solo. A silvicultura só aparece aqui.' },
    { id: 'pevs', nome: 'Silvicultura', un: 'PEVS',
      def: 'Valor da produção da silvicultura no ano mais recente da PEVS e o produto de maior valor no município.' },
  ],
};

// ─── Desenho ───
function semDados() {
  return '<p class="gl-aviso">As listas desta seção vêm de data/glossario.json, que não pôde ser carregado.</p>';
}

function chips(lista) {
  if (!lista?.length) return '';
  return `<div class="gl-chips">${[...lista].sort((a, b) => a.localeCompare(b, 'pt-BR'))
    .map(n => `<span class="gl-chip" data-busca="${norm(n)}">${esc(n)}</span>`).join('')}</div>`;
}

const NIVEL = { agregado: 'agregado', produto: 'produto', especie: 'espécie', contagem: 'contagem' };
// O período só aparece na categoria que não cobre a série inteira, como no seletor.
function chipsPevs(cats, pevs) {
  const [primeiro, ultimo] = pevs?.anos || [];
  const periodo = p => {
    if (!p || !primeiro) return '';
    const [ini, fim] = p;
    if (ini === fim) return `só ${ini}`;
    if (ini > primeiro && fim < ultimo) return `${ini}–${fim}`;
    if (ini > primeiro) return `desde ${ini}`;
    return fim < ultimo ? `até ${fim}` : '';
  };
  return `<div class="gl-chips">${cats.map(c => {
    const extra = [NIVEL[c.nivel] || c.nivel, c.unidade, periodo(c.periodo)].filter(Boolean).join(' · ');
    return `<span class="gl-chip" data-nivel="${esc(c.nivel || '')}" data-busca="${norm(c.categoria + ' ' + extra)}">${esc(c.categoria)}
      <small>${esc(extra)}</small></span>`;
  }).join('')}</div>`;
}

function tabela(prefixo, itens) {
  return `<table class="data-tbl gl-tbl"><thead><tr><th>Métrica</th><th>O que mede</th><th>Cuidado</th></tr></thead><tbody>
    ${itens.map(m => `<tr id="gl-${prefixo}-${m.id}" data-busca="${norm([m.nome, m.un, m.def, m.calc, m.nota].join(' '))}">
      <td>${esc(m.nome)}${m.un ? ` <span class="gl-un">${esc(m.un)}</span>` : ''}</td>
      <td>${esc(m.def)}${m.calc ? `<br><code class="gl-calc">${esc(m.calc)}</code>` : ''}</td>
      <td class="gl-nota" data-rot="Cuidado">${esc(m.nota || '')}</td></tr>`).join('')}
    </tbody></table>`;
}

function linhaFonte(f) {
  const partes = [`${f.base}, ${f.instituicao}`, f.origem, f.periodo, f.nota,
                  f.baixado_em && `baixado em ${f.baixado_em}`].filter(Boolean);
  return `<p class="gl-fonte" data-busca="${norm(partes.join(' '))}">Fonte: ${esc(partes.join('; '))}.</p>`;
}

function secao(id, titulo, corpo, busca = '') {
  return `<section class="gl-sec" id="gl-sec-${id}" data-sec data-busca-titulo="${norm(titulo + ' ' + busca)}">
    <h3>${titulo}</h3>${corpo}</section>`;
}

function render(el, dados, op = {}) {
  const fontes = dados?.fontes || [];
  const fontesDaAba = aba => fontes.filter(f => f.aba === aba).map(linhaFonte).join('');
  const nav = [['ler', 'Como ler'], ['cuidados', 'Cuidados'],
               ...ABAS.map(a => [a.dom, a.nome]), ['concentracao', 'Concentração'],
               ['perfil', 'Perfil do município'], ['fontes', 'Fontes']];

  el.innerHTML = `
  <div class="gl-topo">
    <div class="gl-barra">
      <h2>📖 Glossário</h2>
      ${op.linkPagina ? `<a class="gl-link" href="${op.linkPagina}" target="_blank" rel="noopener">Abrir em página separada ↗</a>` : ''}
    </div>
    <p class="gl-intro">O que cada métrica do painel mede, como é calculada e o que ela <b>não</b> permite concluir,
      com as fontes e o período de cada base. As listas de culturas e de categorias saem dos próprios dados do painel.</p>
    <input class="gl-busca" type="search" placeholder="Buscar: rendimento, módulo fiscal, soja, Gini…"
           aria-label="Buscar no glossário" autocomplete="off">
    <nav class="gl-nav" aria-label="Seções do glossário">
      ${nav.map(([id, nome]) => `<a href="#gl-sec-${id}" data-alvo="sec-${id}">${nome}</a>`).join('')}
    </nav>
  </div>
  <p class="gl-vazio" hidden></p>

  ${secao('ler', 'Como ler o painel', `<table class="data-tbl gl-tbl gl-tbl2"><tbody>
    ${LER.map(([t, d]) => `<tr data-busca="${norm(t + ' ' + d)}"><td>${esc(t)}</td><td>${esc(d)}</td></tr>`).join('')}
    </tbody></table>`)}

  ${secao('cuidados', 'Cuidados ao comparar', `<ul class="gl-lista">
    ${CUIDADOS.map(c => `<li data-busca="${norm(c)}">${esc(c)}</li>`).join('')}</ul>`)}

  ${ABAS.map(a => secao(a.dom, `${a.icone} ${a.nome}`,
    `${fontesDaAba(a.aba)}<p>${esc(a.intro)}</p>${tabela(a.dom, a.metricas)}${a.extra ? a.extra(dados) : ''}`)).join('')}

  ${secao('concentracao', '📊 Concentração', `<p>${esc(CONCENTRACAO.intro)}</p>${tabela('conc', CONCENTRACAO.itens)}`)}

  ${secao('perfil', '🧭 Perfil do município',
    `${fontesDaAba('Perfil do município')}<p>${esc(PERFIL.intro)}</p>${tabela('perfil', PERFIL.itens)}`)}

  ${secao('fontes', 'Fontes e datas', fontes.length ? `
    <table class="data-tbl gl-tbl gl-tbl-fontes"><thead><tr><th>Aba</th><th>Base</th><th>Origem</th><th>Período</th><th>Baixado em</th></tr></thead><tbody>
    ${fontes.map(f => `<tr data-busca="${norm(Object.values(f).join(' '))}">
      <td>${esc(f.aba)}</td><td data-rot="Base"><b>${esc(f.base)}</b><br><span class="gl-sub">${esc(f.instituicao)}</span></td>
      <td data-rot="Origem">${esc(f.origem)}${f.nota ? `<br><span class="gl-sub">${esc(f.nota)}</span>` : ''}</td>
      <td data-rot="Período">${esc(f.periodo)}</td><td data-rot="Baixado em">${esc(f.baixado_em || '—')}</td></tr>`).join('')}
    </tbody></table>
    ${dados?.gerado_em ? `<p class="gl-fonte" style="margin-top:8px">Glossário gerado em ${esc(dados.gerado_em.slice(0, 10).split('-').reverse().join('/'))}.</p>` : ''}`
    : semDados())}`;

  ligarBusca(el);
  el.querySelectorAll('.gl-nav a').forEach(a => a.addEventListener('click', e => {
    e.preventDefault();
    irPara(a.dataset.alvo, false);
    if (op.hash) history.replaceState(null, '', a.getAttribute('href'));
  }));
}

function ligarBusca(el) {
  const busca = el.querySelector('.gl-busca'), vazio = el.querySelector('.gl-vazio');
  busca.addEventListener('input', () => {
    const q = norm(busca.value.trim());
    // Pelo começo das palavras: "car" acha o CAR e não "cana-de-açúcar".
    const re = q && new RegExp('(^|[^a-z0-9])' + q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    let total = 0;
    el.querySelectorAll('[data-sec]').forEach(sec => {
      // A seção cujo título bate aparece inteira.
      const titulo = q && re.test(sec.dataset.buscaTitulo);
      let n = 0;
      sec.querySelectorAll('[data-busca]').forEach(item => {
        const bate = !q || titulo || re.test(item.dataset.busca);
        item.style.display = bate ? '' : 'none';
        if (bate) n++;
      });
      sec.querySelectorAll('.gl-det').forEach(det => {
        const algum = [...det.querySelectorAll('[data-busca]')].some(i => i.style.display !== 'none');
        det.style.display = !q || algum ? '' : 'none';
        det.open = !!q && algum && !titulo;
      });
      sec.querySelectorAll('h4').forEach(h => {
        // O subtítulo some com tudo o que vem embaixo dele até o próximo.
        let x = h.nextElementSibling, algum = false;
        for (; x && x.tagName !== 'H4'; x = x.nextElementSibling)
          if ([x, ...x.querySelectorAll('[data-busca]')].some(i => i.dataset?.busca && i.style.display !== 'none')) algum = true;
        h.style.display = !q || titulo || algum ? '' : 'none';
      });
      const mostra = !q || titulo || n > 0;
      sec.style.display = mostra ? '' : 'none';
      if (mostra) total++;
    });
    vazio.hidden = !q || total > 0;
    vazio.textContent = `Nada encontrado para "${busca.value.trim()}".`;
  });
}

// Rola até a seção ou métrica (`chave` sem o prefixo "gl-") e a destaca.
function irPara(chave, destacar = true) {
  const alvo = document.getElementById('gl-' + chave);
  if (!alvo) return false;
  const busca = alvo.closest('.gl')?.querySelector('.gl-busca');
  if (busca && busca.value) { busca.value = ''; busca.dispatchEvent(new Event('input')); }
  alvo.closest('details')?.setAttribute('open', '');
  alvo.scrollIntoView({ block: destacar ? 'center' : 'start', behavior: 'smooth' });
  if (destacar) {
    alvo.classList.remove('gl-alvo'); void alvo.offsetWidth; alvo.classList.add('gl-alvo');
  }
  return true;
}

function definicao(dom, id) {
  const m = ABAS.find(a => a.dom === dom)?.metricas.find(x => x.id === id);
  return m ? { nome: m.nome, def: m.def, nota: m.nota } : null;
}

return { render, irPara, definicao };
})();
