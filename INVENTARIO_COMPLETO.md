# Inventário Completo — Base AgroCore (pam-dashboard)

> Levantamento profundo de **tudo que existe** na pasta única do projeto
> (`Dados IBGE PAM Culturas/pam-dashboard`) e de **tudo que está de fato
> publicado** em https://boisterous-maamoul-a8039b.netlify.app/
> Gerado em: 2026-08-16 · Atualizado em: 2026-09-26 · Repositório: https://github.com/rschapo/pam-dashboard

---

## Como ler este documento

Este projeto tem **duas camadas bem distintas** e é importante não confundi-las:

1. **PUBLICADO** — o que está de fato no ar, servindo o dashboard público.
2. **BASE COMPLEMENTAR** — dados coletados, processados e validados dentro
   da mesma pasta única (sem duplicação em nenhum outro projeto). Parte já
   alimenta o painel (CAR, economia, uso do solo, tratores e crédito); o resto
   (perfil rural, módulo fiscal, temas do Censo) é insumo para a próxima fase
   (dashboard territorial / cruzamento AOR).

Toda a base usa a mesma chave universal: **`cod_ibge` / `cod_municipio`**
(código IBGE de 7 dígitos). Isso é o que torna tudo abaixo cruzável entre si.

Os **brutos** ficam fora da pasta sincronizada, em
`D:\00-Claude_Fora_Drive\pam-dashboard\raw` (caminho gravado em `data/raw_dir.txt`);
abaixo, `<brutos>` é essa pasta. Em `data/` ficam os processados e os manifestos.

---

## PARTE 1 — O que está PUBLICADO (verificado ao vivo em 2026-09-26, HTTP 200)

| Arquivo | Aba | Tamanho | Cobertura |
|---|---|---|---|
| `data/pkg.json` | 🌾 Agrícola (PAM) | 17,1 MB | 27 UF · 557 microrregiões · 5.540 municípios · 2004–2025 |
| `data/ppm.json` | 🐄 Pecuária (PPM) | 19,2 MB | 27 UF · 558 microrregiões · 5.546 municípios · 2004–2024 |
| `data/pevs.json` | 🌲 Silvicultura (PEVS) | 20,0 MB | 27 UF · 557 microrregiões · 5.474 municípios · 2004–2025 |
| `data/econ.json` | 📊 Economia | 0,6 MB | 5.571 municípios · PIB 2023 · VAB 2021 |
| `data/mapbiomas_mun.json` | 🗺️ Uso do Solo | 0,7 MB | 5.565 municípios · 2024 · Coleção 10.1 |
| `data/maquinas.json` | 🚜 Tratores | 0,3 MB | 5.466 municípios · Censo Agro 2017 (SIDRA 6870) |
| `data/credito.json` | 💰 Crédito | 0,4 MB | 5.465 municípios · 2024 · BCB/SICOR |
| `data/car.json` | 🌳 CAR | 1,3 MB | 5.571 municípios · 27 UF · 5 camadas ambientais · estrutura fundiária |
| `data/geo_uf.json` | Malha de estados | 0,25 MB | 27 UF |
| `data/geo_mic.json` | Malha de microrregiões | 4,3 MB | 558 microrregiões |
| `data/geo_mun.json` | Malha municipal | 16,4 MB | 5.570 municípios |

**O dashboard tem 8 abas de tema** (🌾 Agrícola, 🐄 Pecuária, 🌲 Silvicultura,
📊 Economia, 🗺️ Uso do Solo, 🚜 Tratores, 💰 Crédito, 🌳 CAR) e, conforme o tema,
até 6 visões (Mapa Brasil, Estado/Micro, Municípios, Série Histórica, Rankings,
Concentração). O mapa chega ao **município**: a malha municipal é carregada sob
demanda.

Deploy automático via Netlify a cada push na branch `main`. Conferido em
2026-09-26: `pkg.json`, `pevs.json` e `car.json` no ar são idênticos aos do
repositório.

### Conteúdo detalhado dos domínios publicados

**Agrícola (PAM)** — 81 culturas: Permanentes (36) / Temporárias (45), com os
subgrupos 🌾 Colheitadeiras (14) e 🚜 Tratores (31). Métricas: Área Colhida (ha),
Produção (ton), Valor (mil R$), Rendimento (kg/ha). Fonte: SIDRA tabelas 1612/1613.

**Pecuária (PPM)** — 10 categorias de rebanho + 6 de produção animal (leite, ovos,
mel, lã, casulos). Métricas: Quantidade (unidade varia por categoria) + Valor (mil
R$, só produção animal). Fonte: SIDRA tabelas 3939/74. **A PPM 2025 ainda não saiu**:
em 2026-09-26 as tabelas terminam em 2024, e o calendário do IBGE não traz data até
2027 (a PPM 2024 saiu em 18/09/2025).

**Silvicultura (PEVS)** — 29 categorias de silvicultura (produtos, subtotais e, desde
2013, a abertura por espécie), 62 de extração vegetal e 7 de área plantada. A série
de área plantada começa em 2013. Fonte: SIDRA tabelas 291/289/5930.

**Economia, Uso do Solo, Tratores e Crédito** — indicadores por município, das
bases da Parte 3 (PIB/VAB do IBGE, MapBiomas, Censo Agro 2017 e SICOR).

**CAR** — imóveis, área declarada, cobertura do território e sobreposição, mais as
5 camadas ambientais dissolvidas (vegetação nativa, reserva legal, APP, área
consolidada e uso restrito), em hectares e em % do território, e a estrutura
fundiária: % dos imóveis e da área em pequenos (até 4 módulos fiscais), médios e
grandes (ver 3.3).

---

## PARTE 2 — Pronto e validado, mas AINDA NÃO publicado

| Arquivo | Conteúdo | Municípios |
|---|---|---|
| `data/frontend/perfil_rural.json` | Perfil rural: módulo fiscal, Censo Agro, silvicultura, CAR (com a estrutura fundiária) e MapBiomas | 5.571 |
| `data/processed/dimensions/dim_modulo_fiscal` | Índices básicos do INCRA (módulo fiscal, fração mínima, zona típica) | 5.569 |
| `data/processed/municipality/censo_agro_*` | Temas do Censo Agro 2017 com as categorias (o de máquinas já alimenta a aba Tratores) | 5.563 no resumo |

Os três artefatos da versão anterior desta parte (`geo_mun.json`, `econ.json` e
`mapbiomas_mun.json`) já estão publicados.

**Pendência real:** decidir se o perfil rural entra no painel (aba própria ou painel
lateral do município) e então ligar o `perfil_rural.json` ao frontend.

---

## PARTE 3 — Base complementar completa (dentro da pasta única, `data/`)

Os processados e os manifestos estão em `pam-dashboard/data/` (4,4 GB de
processados); os brutos, em `<brutos>` — **nenhuma duplicação em outro projeto** (a
antiga `Base_Municipios_Brasil` foi auditada, migrada e apagada).

### 3.1 Geografia — ✅ validado

| Tabela | Cobertura | Fonte |
|---|---|---|
| `data/processed/dimensions/dim_municipio.csv` | 5.570 municípios, hierarquia completa (micro/meso/região imediata/intermediária) | IBGE Localidades |
| `<brutos>/ibge/malha_municipios.gpkg` | Malha vetorial municipal (46 MB) | IBGE Malhas v3 |
| `<brutos>/ibge/areas_municipios.csv` | Área territorial (km²) por município | IBGE Áreas Territoriais 2025 |

### 3.2 Uso do solo físico — MapBiomas — ✅ validado

- **Bruto:** `<brutos>/mapbiomas/mapbiomas_cobertura_municipios.xlsx` (77 MB,
  Coleção 10.1) + `mapbiomas_pastagem_municipios.xlsx` (bônus, não
  processado — dados de vigor/idade de pastagem, não simples área)
- **Processado:** `data/processed/municipality/mapbiomas_municipio.csv`
  (295 MB, **3.152.720 linhas**, 5.564/5.570 municípios resolvidos por
  nome+UF — planilha do MapBiomas não traz `cod_ibge` direto)
- **Validação:** total Brasil 2024 = **850,5 Mha** (oficial: 851,6 Mha) ·
  pastagem 155,0 Mha · agricultura 62,7 Mha · silvicultura 8,9 Mha
  (consistente com os 7,69 Mha de eucalipto do PEVS — duas fontes batendo)
- **Bônus:** `car_mapbiomas_comparacao.csv` — reconciliação área CAR ×
  MapBiomas por município, já calculada

### 3.3 Fundiário — CAR (Cadastro Ambiental Rural) — ✅ completo e validado (2026-09)

- **Bruto:** as 135 camadas do SICAR (27 UFs × 5) em `<brutos>/car/` (219 GB
  extraídos), conferidas byte a byte contra os ZIPs; os ZIPs (86 GB, em
  `D:\00-Claude_Fora_Drive\pam-dashboard\car-zips`) ficam guardados por um período.
  Na Bahia, também o CEFIR (`<brutos>/cefir/`).
- **Processado:** `data/processed/geospatial/` — imóveis validados por UF,
  `car_municipio_summary` (cadastros, área geométrica união, sobreposição) e, por
  município, as **5 camadas ambientais dissolvidas** (`car_ambiental_dissolve_<UF>`:
  a área onde cadastros se sobrepõem conta uma vez). BA e SE declaram de outro jeito
  e têm medidas compostas (`car_ambiental_composta_<UF>`). A APP dissolvida soma
  30,7 Mi ha, 3,6% do território.
- **Estrutura fundiária** (`car_estrutura_fundiaria`, 2026-09-26): cada inscrição não
  cancelada classificada pelo número de módulos fiscais (área geométrica ÷ módulo fiscal
  do município). No Brasil, das 8.326.008 inscrições, 93,6% têm até 4 MF, 4,7% de 4 a 15
  e 1,7% mais de 15; somam 24,7%, 16,8% e 58,6% da área cadastrada. A classe bate com a
  que o próprio SICAR calcula em 99,7% das inscrições. Conta inscrições, não
  propriedades, e a área inclui a sobreposição entre cadastros. Entra no perfil rural e
  na aba CAR do painel.
- **Validação contra o MapBiomas** por UF (`processed/state/car_mapbiomas_uf`): na
  mediana das UFs, a vegetação nativa fica em 73% do esperado e a área consolidada em
  86% da agropecuária, com correlações por município de 0,90 e 0,94.
- **Limites e ressalvas por UF:** `generator/complementary/docs/CAR_LIMITATIONS.md`.
  As colunas ambientais do `car_municipio_summary` são soma bruta (contam a
  sobreposição duas vezes); a medida certa é a dissolvida.
- **Nota metodológica:** usar a área *geométrica união*, nunca a *declarada* — CAR é
  autodeclaratório.

### 3.4 Econômico — ✅ validado (2 correções de bug reais)

| Tabela | Cobertura | Números-chave (Brasil, ano mais recente) |
|---|---|---|
| `demografia_pib.csv` (município) + `.csv` (UF) | 5.571 mun / 27 UF | PIB total **R$ 10,94 tri** (2023, bate com oficial) · população **212,58 Mi** (2024) · VAB setorial em **2021** (defasagem real do IBGE — só até esse ano no nível municipal; documentado em `ano_ref_vab`) |
| `credito_rural.csv` | 5.406–5.396 mun (Custeio/Investimento) | Custeio **R$ 208,7 bi** + Investimento **R$ 105,1 bi** (2024). **Bug real corrigido**: o recurso "Investimento" do SICOR/BCB não tem o campo `codIbge` (só código interno do BCB) — a coleta antiga (Base_Municipios_Brasil) vinha sempre 100% nula para essa finalidade. Resolvido por join nome+UF, 99,9% de correspondência |
| `financas.csv` | 5.570 municípios | Receita corrente **R$ 1,17 tri** · Receita total **R$ 1,59 tri** · Transferências correntes **R$ 762 bi** (2023). **Bug real corrigido**: cada conta do DCA-Anexo I-C do SICONFI vem repetida em várias "colunas" do relatório (Receitas Brutas Realizadas / Deduções FUNDEB / Outras Deduções) — a lógica antiga sobrescrevia com a última que aparecesse, pegando valores errados (uma dedução, não o valor bruto). Corrigido filtrando `coluna == "Receitas Brutas Realizadas"` e casando por `cod_conta` exato |

### 3.5 Estrutural — Censo Agropecuário 2017 — achado bônus (alerta de qualidade resolvido)

Localizado durante a consolidação — **não fazia parte do escopo original
desta sessão**, já estava processado de antes:

| Tabela | Conteúdo |
|---|---|
| `censo_agro_machinery.csv` | **Frota de máquinas por município** (tratores etc., SIDRA 6870) — resolve o que o diagnóstico do AOR apontava como bloqueio crítico ("potencial absoluto de máquinas") |
| `censo_agro_land_use.csv`, `_area_groups.csv`, `_land_condition.csv` | Uso da terra, estrutura fundiária declarada |
| `censo_agro_family_farming.csv` | Agricultura familiar |
| `censo_agro_finance.csv`, `_technical_assistance.csv`, `_irrigation.csv`, `_storage.csv`, `_activity.csv` | Financiamento, assistência técnica, irrigação, armazenagem, atividades |
| `censo_agro_municipio_summary.csv` | Resumo por município |

**Alerta de qualidade resolvido em 25/09/2026.** O `numero_estabelecimentos` do
summary somava **10,15 milhões** porque o resumo somava as faixas de área junto com o
Total, e a `area_estabelecimentos_ha` vinha 100% nula. Havia mais: 9 dos 10 temas
tinham perdido a categoria (linhas de um município indistinguíveis), e a armazenagem
vinha da tabela de veículos. Os temas foram baixados de novo com as categorias e com as
tabelas certas (ver `generator/complementary/docs/DATA_DICTIONARY.md`), e o resumo usa
só a linha Total: no Brasil, **5.073.324** estabelecimentos, o número oficial do Censo
2017, e **351,29 milhões de ha** (a área de 6 municípios pequenos é suprimida pelo IBGE).

### 3.6 Governança — TSE (prefeitos eleitos) — ✅ migrado, com limitação conhecida

- `gestao.csv` — 5.567 prefeitos eleitos (mandato 2025–2028)
- **Limitação:** TSE usa código de município próprio (`cod_tse_municipio`),
  diferente do `cod_ibge`. Nunca existiu um de-para TSE↔IBGE neste projeto
  nem no antecessor — os dados ficam **isolados**, não cruzáveis
  automaticamente com o resto da base por enquanto.

### 3.7 Módulo Fiscal (INCRA) — ✅ coletado em 2026-09-26 · SNCR — não coletado

- **Módulo fiscal:** `data/processed/dimensions/dim_modulo_fiscal` — módulo fiscal,
  fração mínima de parcelamento, zona típica de módulo e zona de pecuária em vigor
  (IE INCRA nº 5/2022) para **5.569 municípios**; só Fernando de Noronha e Boa
  Esperança do Norte (MT, instalado em 2025) ficam sem índice. Montado de três peças
  oficiais baixadas automaticamente para `<brutos>/incra/` (tabela de 2013 em PDF,
  planilha da IE de 2022 e a IE no DOU) e conferido contra o trecho do Anexo IV da
  IE: nenhuma divergência em 814 municípios. Já entra no perfil rural
  (`modulo_fiscal_ha`). Método em `generator/complementary/docs/METHODOLOGY.md`.
- **SNCR:** `<brutos>/sncr/` continua vazia — o INCRA publica por UF, sem endpoint
  automatizável; o script (`download_sncr.py`) só inventaria o que for colocado lá.
  Enquanto isso, a estrutura fundiária sai do CAR (3.3).

---

## PARTE 4 — Arquitetura e proveniência

```
pam-dashboard/
├── generator/                    ← pipeline PAM/PPM/PEVS (produção agro) — o que publica o site
│   ├── crop_groups.csv           ← tabela editável de agrupamento de culturas
│   ├── download_{pam,ppm,pevs}_ibge.py
│   └── process_{pam,ppm,pevs}.py → public/data/{pkg,ppm,pevs}.json
│
├── generator/complementary/      ← pipeline territorial (tudo da Parte 3)
│   ├── common.py                 ← utilitários compartilhados (chave cod_ibge, SIDRA client, manifesto)
│   ├── download/                 ← 1 script por fonte (ibge, mapbiomas, car, cefir, censo_agro,
│   │                                demografia_pib, financas, gestao, credito_rural, sncr, modulo_fiscal)
│   ├── process/                  ← 1 script por fonte, mesma convenção
│   ├── config/                   ← land_use_classes.csv, forestry_groups.csv, car_status_map.csv etc.
│   └── docs/                     ← METHODOLOGY.md, DATA_DICTIONARY.md, INTEGRATION_PLAN.md, SOURCES.md,
│                                    QUALITY_REPORT.md, CAR_LIMITATIONS.md, CAR_SOURCE_MATRIX.md
│
├── data/
│   ├── raw_dir.txt   ← aponta os brutos, fora da pasta sincronizada (ibge, mapbiomas, car, cefir,
│   │                    censo_agro, siconfi, bcb, tse, sncr, incra)
│   ├── processed/    ← tabelas finais (dimensions, geospatial, municipality, state), .csv + .parquet
│   ├── frontend/     ← JSON do perfil rural (fora do site)
│   └── manifests/    ← 1 JSON por dataset: fonte, data de extração, hash SHA-256, contagens, avisos
│
└── public/data/      ← o que É PUBLICADO (só o que está commitado no git chega aqui em produção)
```

Todos os manifestos (`data/manifests/*.json`) registram fonte, data de
extração, hash SHA-256 dos arquivos de origem e de saída, contagem de linhas
e avisos — rastreabilidade completa de cada dataset.

**Confirmação de pasta única:** a antiga `Agrocore (Estudos)/Base_Municipios_Brasil`
(0,61 GB, duplicava PAM/PPM/PEVS e tinha 4 camadas únicas) foi totalmente
migrada para dentro desta pasta e **apagada**. Não existe mais nenhuma cópia
paralela de dado de produção agro em nenhum outro projeto.

---

## PARTE 5 — Pendências e cautelas para quem for usar esta base

1. **PPM 2025** — aguardar o IBGE (sem data no calendário em 2026-09-26). Quando
   sair, baixar e regenerar o `ppm.json`; o painel já aceita anos diferentes por aba.
2. **Perfil rural no painel** — o `perfil_rural.json` está pronto, mas ligá-lo ao
   frontend depende de decidir o desenho (ver Parte 2).
3. **Gestão (TSE)** não tem `cod_ibge` — só isolado por enquanto; precisa de
   um de-para TSE↔IBGE para entrar nos cruzamentos.
4. **SNCR** — nada baixado: o INCRA publica por UF, e o download é manual. A estrutura
   fundiária já sai do CAR (3.3); o SNCR a daria no universo do cadastro rural.
5. **CAR** — ler as ressalvas por UF em `CAR_LIMITATIONS.md` antes de comparar
   estados (BA e SE usam as medidas compostas; há UFs com camada parcial na base
   nacional). Os ZIPs do CAR (86 GB) ficam guardados por um período.
6. **`QUALITY_REPORT.md`** está no estado de 2026-07-28 e precisa ser refeito: fora
   o módulo fiscal, ainda marca como pendentes camadas já processadas.
7. Resolvidos desde a versão anterior: publicação de `geo_mun`/`econ`/`mapbiomas_mun`,
   camadas ambientais do CAR (medida dissolvida, 27 UFs), Censo Agropecuário (5.073.324
   estabelecimentos, com as categorias), módulo fiscal e estrutura fundiária pelo CAR.
