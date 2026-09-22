# Inventário Completo — Base AgroCore (pam-dashboard)

> Levantamento profundo de **tudo que existe** na pasta única do projeto
> (`Dados IBGE PAM Culturas/pam-dashboard`) e de **tudo que está de fato
> publicado** em https://boisterous-maamoul-a8039b.netlify.app/
> Gerado em: 2026-08-16 · Repositório: https://github.com/rschapo/pam-dashboard

---

## Como ler este documento

Este projeto tem **duas camadas bem distintas** e é importante não confundi-las:

1. **PUBLICADO** — o que está de fato no ar, servindo o dashboard público.
2. **BASE COMPLEMENTAR** — dados coletados, processados e validados dentro
   da mesma pasta única (sem duplicação em nenhum outro projeto), mas ainda
   **não conectados** ao dashboard público — são o insumo para a próxima
   fase (dashboard territorial / cruzamento AOR).

Toda a base usa a mesma chave universal: **`cod_ibge` / `cod_municipio`**
(código IBGE de 7 dígitos). Isso é o que torna tudo abaixo cruzável entre si.

---

## PARTE 1 — O que está PUBLICADO (verificado ao vivo, HTTP 200)

| Arquivo | Domínio | Tamanho | Cobertura | Status HTTP |
|---|---|---|---|---|
| `data/pkg.json` | 🌾 Agrícola (PAM) | 16,3 MB | 27 UF · 557 microrregiões · 5.536 municípios · 2004–2024 | ✅ 200 |
| `data/ppm.json` | 🐄 Pecuária (PPM) | 19,2 MB | 27 UF · 558 microrregiões · 5.546 municípios · 2004–2024 | ✅ 200 |
| `data/pevs.json` | 🌲 Silvicultura (PEVS) | 17,1 MB | 27 UF · 556 microrregiões · 5.446 municípios · 2004–2024 | ✅ 200 |
| `data/geo_uf.json` | Malha de estados | 0,25 MB | 27 UF | ✅ 200 |
| `data/geo_mic.json` | Malha de microrregiões | 4,3 MB | 558 microrregiões | ✅ 200 |
| `assets/logo.png` | Logo AgroCore | 0,13 MB | — | ✅ 200 |
| `js/main.js` / `css/style.css` | Frontend | — | — | ✅ 200 |

**O dashboard hoje tem 3 domínios navegáveis** (🌾 Agrícola / 🐄 Pecuária /
🌲 Silvicultura), cada um com 5 visões (Mapa Brasil, Estado/Micro,
Municípios, Série Histórica, Rankings), coroplético até o nível de
**microrregião** (não município — a malha municipal já existe mas ainda não
foi ligada, ver Parte 2).

Deploy automático via Netlify a cada push na branch `main`. Commit publicado
mais recente: `0a1d365` (banner de consentimento de cookies / LGPD).

### Conteúdo detalhado dos 3 domínios publicados

**Agrícola (PAM)** — 67 culturas, agrupadas em Permanentes (33) / Temporárias
(34) / 🌾 Colheitadeiras (14, subgrupo de grãos) / 🚜 Tratores (20, subgrupo
calculado). Métricas: Área Colhida (ha), Produção (ton), Valor (mil R$),
Rendimento (kg/ha). Fonte: SIDRA tabelas 1612/1613.

**Pecuária (PPM)** — 10 categorias de rebanho (Bovino, Bubalino, Caprino,
Codornas, Equino, Galináceos, Ovino, Suíno) + 6 de produção animal (Leite,
Ovos de galinha/codorna, Mel, Lã, Casulos do bicho-da-seda). Métricas:
Quantidade (unidade varia por categoria) + Valor (mil R$, só produção
animal). Fonte: SIDRA tabelas 3939/74.

**Silvicultura (PEVS)** — 21 produtos de floresta plantada (carvão vegetal,
lenha, madeira em tora — hierárquicos) + 52 de extração vegetal nativa + 3
espécies de área plantada (Eucalipto/Pinus/Outras). Fonte: SIDRA tabelas
291/289/5930.

---

## PARTE 2 — Pronto e validado, mas AINDA NÃO publicado

Estes arquivos já existem em `public/data/` **localmente**, prontos no
formato que o frontend consome, mas **não foram commitados nem deployados**
(confirmado: HTTP 404 no site ao vivo). Foram gerados por uma sessão anterior
(11/08) a partir dos dados processados descritos na Parte 3.

| Arquivo local | Conteúdo | Tamanho | Municípios |
|---|---|---|---|
| `public/data/geo_mun.json` | Malha municipal (Brasil inteiro) | 15,6 MB | 5.570, chave `{cod_ibge, uf}` |
| `public/data/econ.json` | PIB/VAB por município e UF (versão compacta) | 0,6 MB | 5.571 |
| `public/data/mapbiomas_mun.json` | Uso do solo por município (versão compacta) | 0,66 MB | 5.565 |

**O que isso destrava, quando conectado:** coroplético em nível de
**município** (hoje só microrregião), e dois domínios novos possíveis —
contexto econômico (PIB/VAB) e uso físico do solo (MapBiomas) — como 4º/5º
domínio do dashboard, ou como camadas de contexto dentro dos domínios
existentes.

**Pendência real:** decidir o desenho de UI (novo domínio? camada de mapa
adicional? painel lateral?) e então: `git add -f public/data/{geo_mun,econ,mapbiomas_mun}.json`
+ trecho de frontend + commit + push.

---

## PARTE 3 — Base complementar completa (dentro da pasta única, `data/`)

Tudo abaixo está em `pam-dashboard/data/` (raw + processed + manifests) —
**nenhuma duplicação em outro projeto** (a antiga `Base_Municipios_Brasil`
foi auditada, migrada e apagada nesta mesma sessão de trabalho).

### 3.1 Geografia — ✅ validado

| Tabela | Cobertura | Fonte |
|---|---|---|
| `data/processed/dimensions/dim_municipio.csv` | 5.570 municípios, hierarquia completa (micro/meso/região imediata/intermediária) | IBGE Localidades |
| `data/raw/ibge/malha_municipios.gpkg` | Malha vetorial municipal (46 MB) | IBGE Malhas v3 |
| `data/raw/ibge/areas_municipios.csv` | Área territorial (km²) por município | IBGE Áreas Territoriais 2025 |

### 3.2 Uso do solo físico — MapBiomas — ✅ validado nesta sessão

- **Bruto:** `data/raw/mapbiomas/mapbiomas_cobertura_municipios.xlsx` (77 MB,
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

### 3.3 Fundiário — CAR (Cadastro Ambiental Rural) — ⚠️ presente, não auditado nesta sessão

- **Bruto:** `data/raw/car/<UF>/` — 27 estados, shapefiles/geojson de
  imóveis, APP, reserva legal, vegetação nativa, uso restrito, área
  consolidada (**11 GB total**)
- **Processado:** `data/processed/geospatial/` (**3,9 GB**) — parquets de
  imóveis validados por UF + `car_municipio_summary.csv`:
  - 5.562 municípios · **8.267.002 cadastros** (8.266.504 válidos)
  - Área geométrica união (pegada física real): **587,1 Mha** (~69% do
    território nacional — plausível para um cadastro autodeclaratório)
  - Colunas de vegetação nativa/reserva legal/APP/área consolidada
    **presentes mas parecem subpopuladas** nacionalmente (somas muito baixas
    — 13,4 Mha de vegetação nativa é implausível para o Brasil todo; a
    camada ambiental parece ter sido processada só para alguns estados via
    `car_ambiental_municipio_<UF>.csv`). **Não validei este ponto — revisar
    antes de usar essas colunas específicas.**
- **Nota metodológica (já documentada no projeto):** usar a área
  *geométrica união*, nunca a *declarada* — CAR é autodeclaratório.

### 3.4 Econômico — ✅ validado nesta sessão (2 correções de bug reais)

| Tabela | Cobertura | Números-chave (Brasil, ano mais recente) |
|---|---|---|
| `demografia_pib.csv` (município) + `.csv` (UF) | 5.571 mun / 27 UF | PIB total **R$ 10,94 tri** (2023, bate com oficial) · população **212,58 Mi** (2024) · VAB setorial em **2021** (defasagem real do IBGE — só até esse ano no nível municipal; documentado em `ano_ref_vab`) |
| `credito_rural.csv` | 5.406–5.396 mun (Custeio/Investimento) | Custeio **R$ 208,7 bi** + Investimento **R$ 105,1 bi** (2024). **Bug real corrigido**: o recurso "Investimento" do SICOR/BCB não tem o campo `codIbge` (só código interno do BCB) — a coleta antiga (Base_Municipios_Brasil) vinha sempre 100% nula para essa finalidade. Resolvido por join nome+UF, 99,9% de correspondência |
| `financas.csv` | 5.570 municípios | Receita corrente **R$ 1,17 tri** · Receita total **R$ 1,59 tri** · Transferências correntes **R$ 762 bi** (2023). **Bug real corrigido**: cada conta do DCA-Anexo I-C do SICONFI vem repetida em várias "colunas" do relatório (Receitas Brutas Realizadas / Deduções FUNDEB / Outras Deduções) — a lógica antiga sobrescrevia com a última que aparecesse, pegando valores errados (uma dedução, não o valor bruto). Corrigido filtrando `coluna == "Receitas Brutas Realizadas"` e casando por `cod_conta` exato |

### 3.5 Estrutural — Censo Agropecuário 2017 — ⚠️ achado bônus, com alerta de qualidade

Localizado durante a consolidação — **não fazia parte do escopo original
desta sessão**, já estava processado de antes:

| Tabela | Conteúdo |
|---|---|
| `censo_agro_machinery.csv` | **Frota de máquinas por município** (tratores etc., SIDRA 6870) — resolve o que o diagnóstico do AOR apontava como bloqueio crítico ("potencial absoluto de máquinas") |
| `censo_agro_land_use.csv`, `_area_groups.csv`, `_land_condition.csv` | Uso da terra, estrutura fundiária declarada |
| `censo_agro_family_farming.csv` | Agricultura familiar |
| `censo_agro_finance.csv`, `_technical_assistance.csv`, `_irrigation.csv`, `_storage.csv`, `_activity.csv` | Financiamento, assistência técnica, irrigação, armazenagem, atividades |
| `censo_agro_municipio_summary.csv` | Resumo por município |

**⚠️ Alerta de qualidade encontrado agora:** o total nacional de
`numero_estabelecimentos` no summary soma **10,15 milhões** — o número
oficial do Censo Agropecuário 2017 é **~5,07 milhões** de estabelecimentos.
Parece dupla contagem (provavelmente somando categorias/subgrupos junto com
um total). **Não usar esse total nacional até revisar** — os dados por
município podem estar corretos individualmente, mas a agregação não bate.
`area_estabelecimentos_ha` está **100% nula** nesta tabela.

### 3.6 Governança — TSE (prefeitos eleitos) — ✅ migrado, com limitação conhecida

- `gestao.csv` — 5.567 prefeitos eleitos (mandato 2025–2028)
- **Limitação:** TSE usa código de município próprio (`cod_tse_municipio`),
  diferente do `cod_ibge`. Nunca existiu um de-para TSE↔IBGE neste projeto
  nem no antecessor — os dados ficam **isolados**, não cruzáveis
  automaticamente com o resto da base por enquanto.

### 3.7 Módulo Fiscal / SNCR / INCRA — não coletado

`data/raw/sncr/` e `data/raw/incra/` existem como pastas vazias — scripts de
coleta (`download_modulo_fiscal.py`, `process_sncr.py` etc.) já prontos em
`generator/complementary/`, mas sem dado bruto baixado ainda.

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
│   ├── download/                 ← 1 script por fonte (ibge, mapbiomas, car, censo_agro, demografia_pib,
│   │                                financas, gestao, credito_rural, sncr, modulo_fiscal)
│   ├── process/                  ← 1 script por fonte, mesma convenção
│   ├── config/                   ← land_use_classes.csv, forestry_groups.csv, car_status_map.csv etc.
│   └── docs/                     ← METHODOLOGY.md, DATA_DICTIONARY.md, INTEGRATION_PLAN.md, SOURCES.md,
│                                    QUALITY_REPORT.md, CAR_LIMITATIONS.md, CAR_SOURCE_MATRIX.md
│
├── data/
│   ├── raw/          ← arquivos brutos por fonte (ibge, mapbiomas, car, censo_agro, siconfi, bcb, tse, sncr, incra)
│   ├── processed/    ← tabelas finais (dimensions, geospatial, municipality, state), .csv + .parquet
│   └── manifests/    ← 1 JSON por dataset: fonte, data de extração, hash SHA-256, contagens, avisos
│
└── public/data/      ← o que É PUBLICADO (só o que está commitado no git chega aqui em produção)
```

Todos os manifestos (`data/manifests/*.json`) registram fonte, data de
extração, hash SHA-256 dos arquivos de origem e de saída, contagem de linhas
e avisos — rastreabilidade completa de cada dataset.

**Confirmação de pasta única:** a antiga `Agrocore (Estudos)/Base_Municipios_Brasil`
(0,61 GB, duplicava PAM/PPM/PEVS e tinha 4 camadas únicas) foi totalmente
migrada para dentro desta pasta e **apagada** nesta sessão. Não existe mais
nenhuma cópia paralela de dado de produção agro em nenhum outro projeto.

---

## PARTE 5 — Pendências e cautelas para quem for usar esta base

1. **Publicar os 3 novos artefatos da Parte 2** (`geo_mun.json`, `econ.json`,
   `mapbiomas_mun.json`) exige decisão de design de UI antes do
   commit+push — hoje eles só existem localmente.
2. **CAR — colunas ambientais** (vegetação nativa, reserva legal, APP,
   área consolidada) parecem incompletas nacionalmente — revisar antes de
   usar para qualquer análise de "pegada ambiental".
3. **Censo Agropecuário — `numero_estabelecimentos`** está com total
   nacional ~2× o valor oficial — investigar dupla contagem antes de citar
   esse agregado (os dados de máquinas/frota parecem OK, é especificamente
   o resumo de estabelecimentos que está suspeito).
4. **Gestão (TSE)** não tem `cod_ibge` — só isolado por enquanto; precisa de
   um de-para TSE↔IBGE para entrar nos cruzamentos.
5. **SNCR, INCRA, Módulo Fiscal** — scripts prontos, nada baixado ainda.
6. Todo o resto (PAM, PPM, PEVS, geo_mun, MapBiomas, demografia_pib,
   crédito rural, finanças) foi **validado nesta sessão** contra números
   oficiais conhecidos e bate.
