# Receita Federal: contas-chave e produtores rurais

Duas camadas tiradas da base de Dados Abertos CNPJ da Receita Federal, para o painel público
do Brasil (sem marca, sem concessionário). Período em uso: o de `PERIODO_ATUAL.txt` da base
(`D:\00-Claude_Fora_Drive\Dados Receita Federal\CNPJ`), hoje **2026-10** (extração da Receita
com aberturas até 11/10/2026).

| Camada | Script | O que o painel recebe |
|---|---|---|
| Contas-chave da agroindústria | `process/process_contas_chave.py` | `public/data/contas_chave.json`: nº de estabelecimentos por município e setor; nas usinas, a capacidade autorizada de etanol somada |
| Produtores rurais | `process/process_produtores.py` | `public/data/produtores_mun.json`: nº de cadastros ativos e abertos nos últimos 24 meses, por município × atividade × tipo |

Rodar, a partir de `generator/complementary` (o `.venv` tem o DuckDB):

```bash
.venv/Scripts/python.exe download/download_anp_etanol.py
.venv/Scripts/python.exe process/process_contas_chave.py
.venv/Scripts/python.exe process/process_produtores.py
.venv/Scripts/python.exe quality/verificar_lgpd_publico.py
```

Cada consulta leva menos de 30 s (DuckDB só leitura, 20 GB de memória no máximo, arquivos
temporários em `D:\00-Claude_Fora_Drive\pam-dashboard\duckdb_tmp`).

## Regra de dados pessoais (decisão do usuário, 21/10/2026)

- Painel de concessionário, privado e com senha: lista nominal dos produtores (opção D). **Não é
  este painel.**
- Este painel, público: **opção A, só contagens anônimas** por município e atividade. Nada que
  identifique pessoa chega a `public/`: nem nome, CPF/CNPJ de pessoa física, endereço, CEP,
  telefone, e-mail, coordenada, data de abertura individual ou razão social de produtor rural
  pessoa física.
- A base com identificador fica **só** no cache local, fora do OneDrive e fora do projeto:
  `D:\00-Claude_Fora_Drive\pam-dashboard\receita_cache` (ou `PAM_CACHE_PF`, ou o caminho em
  `data/cache_pf_dir.txt`). `receita_common.pf_cache_dir()` recusa qualquer pasta dentro do
  projeto ou do OneDrive.
- **Lista de exclusão** (opt-out): `<cache>/exclusoes_lgpd.csv` (`cnpj;data;canal;responsavel`;
  CNPJ completo exclui o estabelecimento, CNPJ raiz de 8 dígitos exclui todos). Aplicada antes de
  contar e antes de gravar a base local. Fica no cache, nunca no git: a própria lista identifica
  quem pediu para sair.
- **Supressão de célula pequena**: desligada por padrão (a contagem vem de cadastro público e não
  revela atributo novo de ninguém). `process_produtores.py --suprimir-abaixo 3` trocaria as
  contagens de 1 e 2 por `null` e grava o limite em `suprimido_abaixo`. Decisão pendente do
  usuário.
- Sem sócios (QSA) em nenhuma das duas camadas.
- Testes: `tests/test_lgpd_publico.py` varre o `public/` como está (CNPJ com e sem máscara,
  telefone, "@" nos JSON de dados, chaves de identificação nos JSON de produtores e contas, e uma
  amostra de 500 nomes de produtores PF sorteados da base local, por frase inteira) e inclui
  testes que injetam um nome e um CNPJ num arquivo temporário para provar que o verificador acusa.

## Contas-chave

Estabelecimentos **ativos** (situação 02), **CNAE principal**, 27 UFs, **só natureza jurídica
2xxx** (entidades empresariais, cooperativas incluídas).

| Setor (chave no painel) | Regra |
|---|---|
| Usina com autorização da ANP (`usina_anp`) | CNAE 1071-6/00 (açúcar em bruto), 1072-4/01 (açúcar refinado) ou 1931-4/00 (álcool), ou qualquer CNAE se o CNPJ completo for uma planta com capacidade autorizada de etanol na ANP |
| CNAE de usina sem autorização (`usina_conf`) | CNAE de usina sem planta da ANP no CNPJ, com capital social ≥ R$ 1 mi OU capital não informado (0,00 ou vazio) e porte "05 — Demais": confirmar (pode ser só de açúcar, escritório, refinaria, comercializadora, ou em recuperação judicial). Fica fora com capital informado abaixo de R$ 1 mi (desde 22/10/2026; no RS, quase todos fabricantes de melado, açúcar mascavo e álcool artesanal) ou com capital não informado e porte ME/EPP (23/10/2026: capital 0,00 é campo não preenchido; em SP, 43 usinas sem ANP com capital zero e porte Demais, muitas S.A. com USINA, DESTILARIA ou AÇÚCAR na razão social, voltaram). O detalhe local traz a coluna `capital_nao_informado` e a validação, `confirmar_com_capital_nao_informado` |
| Unidade agrícola de grupo sucroenergético (`usina_agricola`) | CNAE 0113-0/00 (cana) de um CNPJ raiz que tem usina: mostra onde o grupo opera, não é usina a mais |
| Sucos (`sucos`) | CNAE 1033-3/01 com capital social ≥ R$ 1 mi |
| Pós-colheita (`pos_colheita`) | CNAE 0163-6/00 |
| Café (`cafe`) | CNAE 1081-3/01 (beneficiamento) ou 4621-4/00 (atacado de café em grão) |
| Florestal (`florestal`) | CNAE 1710-9/00 (celulose), ou 0210-1/01 (eucalipto) com capital ≥ R$ 1 mi |
| Cooperativa agropecuária (`cooperativa`) | natureza 2143 com CNAE das divisões 01, 10 ou 46 |

A ordem de prioridade é a da tabela: um estabelecimento entra num setor só. O capital social vem
como texto pt-BR ("1.234,56"); o porte "05 — Demais" da Receita é tudo o que não é ME/EPP e não
separa a empresa grande, por isso o corte é pelo capital.

**ANP.** `download/download_anp_etanol.py` baixa o `pb-da-etanol.zip` do Painel Dinâmico de
Produtores de Etanol para `<brutos>/anp/pb-da-etanol_<data>.zip`, com SHA-256 no manifesto
`data/manifests/raw_anp_etanol.json`. Vale o último mês de "Etanol_Capacidade 2021-2026.csv";
o separador é detectado, a codificação é UTF-8 com BOM (com recuo para latin-1, que era a de
versões anteriores) e as colunas são lidas pela posição. A UF da ANP é comparada só pelas letras
ASCII.

**Município.** A Receita usa código de município próprio. O casamento é por (nome normalizado, UF)
contra a `dim_municipio`, feito sobre os ~5,4 mil pares distintos e não linha a linha. Os nomes
que a Receita grafa diferente estão em `config/aliases_municipio_rfb.csv` (12, revisados à mão:
Parati/Paraty, Boa Saúde/Januário Cicco, Fortaleza do Tabocão/Tabocão…). Só "EXTERIOR" fica sem
par.

**Posição no mapa.** Ponto representativo do polígono do município (`geo_mun.json`): precisão
municipal, nunca endereço. Boa Esperança do Norte (MT, instalado em 2025) ainda não está na malha
e fica sem ponto (`"xy": null`).

Nomes de empresas não vão ao painel por padrão: a razão social de pessoa jurídica não é dado
pessoal, e a lista de plantas da ANP já é pública, mas publicar é decisão do usuário. **Se um dia
publicarem nomes, excluir as naturezas 2135 (empresário individual), 2305 e 2313 (EIRELI)**: a
razão social delas costuma ser o nome de uma pessoa. Hoje há 811 estabelecimentos de natureza 2135
entre as contas-chave.

## Produtores rurais

Universo: estabelecimentos ativos com CNAE principal das divisões **01** (agricultura, pecuária e
serviços) e **02** (produção florestal), 27 UFs, todas as naturezas.

- **Tipo**: `PF` = natureza 4120 (Produtor Rural, pessoa física); `PJ` = natureza 2xxx; `outra` =
  as demais (associações, órgãos públicos…).
- **Atividade**: pelo CNAE principal, na tabela `config/cnae_atividade_produtores.csv` — as 100
  subclasses 01 e 02 da tabela de CNAE da Receita, uma por linha, com o grupo: cana, citros, café,
  grãos (cereais, oleaginosas e fibras de lavoura temporária, feijão), H&F (horticultura, frutas
  de lavoura permanente exceto laranja, melão, melancia, abacaxi, alho, batata-inglesa, cebola,
  tomate rasteiro, uva), bovinos, aves e suínos (com caprinos, ovinos, equinos e demais animais),
  florestal (toda a divisão 02), serviços (grupo 016, inclusive pós-colheita e serviço com
  máquinas) e outros (fumo, mandioca, flores, cacau, erva-mate, dendê, seringueira, sementes,
  caça…). CNAE fora da tabela para a rodada.
- **Abertos nos últimos 24 meses**: data de início de atividade a partir de 24 meses antes da
  data de referência do período (a abertura mais recente da base: 11/10/2026 → corte em
  11/10/2024).

### Cuidados (vão também ao glossário)

- Cadastro na Receita ≠ estabelecimento agropecuário do Censo: muitos produtores operam só com CPF
  e inscrição estadual e não têm CNPJ.
- Um produtor pode ter vários cadastros (um por imóvel ou inscrição estadual).
- A atividade é o CNAE declarado, que pode não ser a atividade real.
- **A cobertura muda de estado para estado.** Em SP há 737 mil cadastros ativos para 189 mil
  estabelecimentos do Censo 2017 (razão 3,9), com 20 a 28 mil aberturas de produtor PF por ano
  desde 2012; nas demais UFs a razão vai de 0,8% (CE, PI, PB) a 31% (DF). O padrão de SP indica
  que lá o cadastro estadual do produtor rural passa pelo CNPJ — hipótese a confirmar com a regra
  da Sefaz-SP. Por isso a contagem não serve para comparar UFs entre si, só municípios da mesma UF.

## Onde fica cada arquivo

| Arquivo | Conteúdo | Onde |
|---|---|---|
| `contas_chave_detalhe_<período>.parquet` | um estabelecimento por linha, com CNPJ, razão social e setor | cache local (fora do OneDrive) |
| `produtores_base_<período>.parquet` | um cadastro por linha, com CNPJ, natureza, CNAE, município, data de início e razão social | cache local (fora do OneDrive) |
| `exclusoes_lgpd.csv` | lista de exclusão | cache local (fora do OneDrive) |
| `data/processed/municipality/contas_chave_municipio` | município × setor: estabelecimentos e capacidade ANP | projeto (sem identificador) |
| `data/processed/municipality/produtores_municipio` | município × atividade × tipo: ativos e novos 24 meses | projeto (sem identificador) |
| `data/manifests/contas_chave.json`, `produtores_rurais.json`, `raw_anp_etanol.json` | validação e rastreabilidade (só contagens) | projeto |
| `public/data/contas_chave.json`, `produtores_mun.json` | o que o painel publica | projeto |
