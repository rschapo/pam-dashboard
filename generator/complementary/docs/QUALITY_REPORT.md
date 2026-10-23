# QUALITY_REPORT — Relatório de qualidade

## Atualização de 21/10/2026 (painel Brasil: densidades, cultura dominante, Receita)

### Erros encontrados e corrigidos (dado oficial não foi mexido)

- **Café contado duas vezes desde 2012.** A PAM publica "Café (em grão) Total" e as partes
  Arábica e Canephora; o `process_pam.py` somava as três em Todas as Culturas, Permanentes,
  microrregião e município, e o front somava as três no estado. Em 2025, a área colhida do
  Brasil saía 102,58 Mha em vez de 100,64 Mha (+1,94 Mha, 1,9%); a produção e o valor, na
  mesma proporção do café. Agora as partes têm `pai` no `crop_groups.csv`, ficam fora de todo
  agregado e continuam selecionáveis uma a uma. Conferido: a diferença no `pkg.json` é
  exatamente a área das partes, só de 2012 em diante, e `est_data` e os grupos TEM, COL e TRA
  não mudaram.
- **Cultura escolhida no mapa de municípios mostrava o grupo.** O `pkg.json` só tinha o
  município pelo total e pelos grupos: escolhida a soja, o ranking e o mapa municipal
  mostravam a área de todas as culturas do grupo. Agora há um arquivo por cultura
  (`public/data/pam_mun/`), baixado quando a cultura é escolhida; a soma municipal da soja em
  SP (1.376.075 ha em 2025) bate com o total estadual.
- **Legenda do mapa Brasil não correspondia às cores.** As cores seguem escala logarítmica, e a
  legenda mostrava frações lineares do máximo (o segundo tom aparecia como "1/6 do máximo",
  quando cobre valores mil vezes menores). A legenda passou a mostrar a faixa de cada tom.
- **KPI "Culturas" contava pares estado × cultura** (1.057 no Brasil); agora conta culturas
  distintas: 70 em 2025 (as 72 linhas de cultura da PAM no ano menos as duas partes do café).
- **JSON com NaN**: nenhum arquivo publicado tinha NaN, mas nenhum export recusava NaN ao
  gravar. Todos os exports passam por `common.write_public_json` (NaN → null e
  `allow_nan=False`); PAM, PPM, PEVS e a malha municipal gravam com `allow_nan=False`. Os seis
  JSON reexportados para conferir saíram idênticos aos publicados.

### Conferências que passaram

- PAM: em toda a série, a soma municipal da área colhida bate com o total estadual publicado
  pelo IBGE (`PAM_estados.csv`); em 2025, nas 1.087 combinações UF × cultura. Nenhuma exceção
  a registrar (`tests/test_pam_consistencia.py` aceita divergência só se ela for registrada).
- Ausente ≠ zero nas camadas novas: município sem nenhuma lavoura no PAM do último ano fica
  sem valor (cinza), com PAM e sem a cultura fica zero; na PEVS, quem não aparece não tem
  floresta plantada.
- Cada pesquisa no próprio último ano: densidades prontas e cultura dominante usam PAM 2025 e
  PEVS 2025 e dizem isso na legenda, nos KPIs e no seletor de ano.
- Grupos e cultura dominante: soma municipal de cada grupo = soma estadual das culturas dele
  (soja 47,6 Mha, cana 10,2 Mha, floresta plantada 10,4 Mha em 2025); nenhuma parte do café em
  grupo ou categoria (o export aborta se entrar).

### Cultura dominante (2025): municípios por categoria

Grãos e oleaginosas 2.986 · Floresta plantada 801 · Cana 609 · Frutas 292 · Café 270 ·
Mandioca 240 · Outras lavouras 103 · Hortaliças e legumes 91 · Cacau 77 · Citros 50 · sem
lavoura nem floresta publicadas 52. A floresta aparece forte porque a comparação é de área
colhida (PAM) com área plantada (PEVS), e isso está na legenda e no glossário.

### Rio Grande do Sul (foco pedido em 21/10/2026)

- 497 municípios, 26,9 Mha de território. Cultura dominante: Grãos 391, Floresta plantada 73
  (acácia-negra, eucalipto e pinus, na encosta e no litoral norte), Frutas 22 (uva), Citros 4,
  Outras 4, Mandioca 2, sem dado 1.
- Grãos esconde o arroz, que é a lavoura de maior área em 37 municípios (971 mil ha): por isso
  entraram os atalhos de densidade Arroz, Trigo (1,16 Mha) e Fumo (159 mil ha). Densidade de
  arroz mais alta em Arambaré e Tapes (planície costeira).
- Fumo e erva-mate com categoria própria dominariam só 2 municípios cada no RS (fumo 7 no
  Brasil): ficam em Outras lavouras.
- Produtores (Receita): o RS não tem nenhum cadastro de produtor pessoa física com CNPJ; os
  15.646 cadastros são de pessoa jurídica (15.486) e outras naturezas (160), metade de
  serviços agropecuários. Contra 365.094 estabelecimentos do Censo 2017, razão 0,043.
- Contas-chave: 1.539 estabelecimentos de cooperativas agropecuárias, concentrados no Planalto.

### Atualização de 22/10/2026: Censo 2017 nos Produtores e corte nas usinas a confirmar

- **Produtores comparáveis entre estados.** O domínio Produtores passou a abrir no Censo
  Agropecuário 2017 (SIDRA 6778, estabelecimentos por atividade predominante e por
  tipologia), que recenseia todo estabelecimento com CPF ou CNPJ. A Receita fica como
  segunda fonte. O RS sai de 15.646 cadastros (Receita, só PJ) para 365.094 estabelecimentos
  (Censo): 193.626 em lavouras temporárias, 130.391 em pecuária, 20.064 em lavouras
  permanentes, 12.197 em florestas plantadas; 293.892 de agricultura familiar (80,5%; SP:
  122.555 de 188.620, 65,0%). A tabela foi baixada de novo com o símbolo de cada célula,
  porque o coletor antigo gravava o "-" (zero) e o "X" (sigilo) como o mesmo vazio; a
  contagem de estabelecimentos não tem sigilo em nenhum município. Soma municipal =
  5.073.324, o total oficial.
- **Usinas "a confirmar" só com capital ≥ R$ 1 mi.** No RS, 98 dos 109 estabelecimentos com
  CNAE de açúcar ou álcool sem autorização da ANP tinham capital abaixo de R$ 1 mi (mediana
  de R$ 10 mil): fabricantes de melado, açúcar mascavo e álcool artesanal, e não usinas. Com
  o corte, "a confirmar" cai de 1.370 para 410 no Brasil (SP 256 → 106, RS 109 → 11); 964
  estabelecimentos saem. As unidades agrícolas de grupo caem de 2.169 para 2.056, porque a
  fazenda só conta quando a raiz tem usina, e 16 cooperativas pequenas com CNAE de açúcar
  passam a contar como cooperativa.
- **23/10/2026: capital 0,00 é capital não informado** (decisão do usuário, repassada pela
  sessão do painel do concessionário de SP). Usina sem ANP com capital zero (ou vazio) e
  porte "Demais" volta para "a confirmar"; só sai quem tem capital informado abaixo de
  R$ 1 mi, ou capital não informado e porte ME/EPP. Em SP, 43 dos 87 que a regra anterior
  derrubava tinham capital zero e porte Demais, muitas sociedades anônimas com USINA,
  DESTILARIA ou AÇÚCAR na razão social: provavelmente usinas reais (só de açúcar, que não
  pedem autorização de etanol à ANP). "A confirmar": Brasil 410 → 615 no painel (619
  estabelecimentos; 209 com capital não informado), SP 106 → 149, RS 11 → 14. Unidades
  agrícolas de grupo: 2.056 → 2.166 (SP 1.721).

### Receita: contas-chave e produtores (CNPJ 2026-10, ANP 09/2026)

- ANP × Receita: 370 plantas autorizadas (442.294 m³/d); 367 ativas na Receita, 3 inativas, 0
  não encontradas. Das 1.724 com CNAE de usina na Receita, 350 têm autorização da ANP e 1.374
  ficam "confirmar"; 17 plantas da ANP estão com outro CNAE e entram como usina. 177 usinas têm
  "recuperação judicial" na razão social.
- Município: 12 grafias da Receita resolvidas em `config/aliases_municipio_rfb.csv`; só
  "EXTERIOR" sem par (23 contas-chave, 186 cadastros de produtor, fora dos agregados). Boa
  Esperança do Norte (MT) sem ponto na malha (o círculo dela não é desenhado).
- **Cobertura dos produtores**: o produtor rural pessoa física só aparece com CNPJ em SP
  (694.280) e AL (722). Nas outras 25 UFs ele opera com CPF e inscrição estadual e não está na
  base. Razão cadastros ÷ estabelecimentos do Censo 2017: SP 3,909; DF 0,311; MS 0,165; MT
  0,154; GO 0,108; RJ 0,090; PR 0,065; TO 0,059; SC 0,053; MG 0,050; RS 0,043; ES 0,042; AP
  0,036; RR 0,033; RN 0,027; RO 0,025; PA 0,020; AL 0,020; AM 0,018; MA 0,015; AC 0,014; BA
  0,014; PE 0,013; SE 0,009; PI 0,008; CE 0,008; PB 0,008. Nada corrigido: são universos
  diferentes. O domínio Produtores abre em pessoa jurídica e avisa, acima do mapa, que não se
  comparam estados.
- Não-identificação: `quality/verificar_lgpd_publico.py` e `tests/test_lgpd_publico.py` sem
  achados em `public/` (CNPJ, telefone, @, chaves de identificação, amostra de 500 nomes de
  pessoa física da base local).

---

Estado em 2026-07-28 (o que segue é o relatório anterior). Este relatório distingue o que foi **efetivamente processado**
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
