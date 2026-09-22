# INITIAL_ASSESSMENT — Etapa 0 (Inventário e Diagnóstico)

Projeto: Dashboard Agrocore — bases complementares fundiárias, produtivas e ambientais.
Data do diagnóstico: 2026-07-28. Escopo: Etapas 1 e 2 (sem junção definitiva com `pkg.json`/`ppm.json`).

## 1. O que já existe no repositório `pam-dashboard`

O repositório está organizado em `generator/` (geração de dados, roda localmente) e
`public/` (publicado no Netlify). Os geradores existentes seguem um padrão maduro e
consistente, que a base complementar reaproveita integralmente:

- `generator/process_pam.py`, `generator/download_ppm_ibge.py`/`process_ppm.py`,
  `generator/download_pevs_ibge.py`/`process_pevs.py` e `generator/ibge_common.py`.
- Coleta SIDRA com **descoberta de metadados** (variáveis e classificações resolvidas
  por nome em tempo de execução via `v3/agregados/{tabela}/metadados` e `/periodos`),
  o que torna o coletor robusto a mudanças de numeração. A consulta de valores usa
  `n6` (município) filtrado por `n3` (UF), **uma UF por vez**, com salvamento
  progressivo por ano e retomada automática.
- `Cod_Municipio` tratado como **texto de 7 dígitos**; CSVs em `;` e `utf-8-sig`;
  limpeza de nulos SIDRA (`-`, `..`, `X` → `None`, nunca zero).
- Saídas JSON com a tríade `est_data` / `mic_data` / `mun_data` e dicionários
  `ufs_info` / `mic_info` / `mun_info`. Os arquivos `pkg.json` (PAM, 16 MB) e
  `ppm.json` (PPM, 19 MB) já existem e **não devem ser alterados** nesta fase.
- Chaves geográficas disponíveis: `geo_uf.json` e `geo_mic.json` (UF e microrregião);
  **não há malha municipal** publicada no repositório — necessária para a interseção
  espacial do CAR (Etapa 2).

Base-mestra paralela (`Agrocore (Estudos)/Base_Municipios_Brasil`): já possui
`scripts/coletar_base.py` (idempotente), `DICIONARIO_DE_DADOS.md`, e — o achado mais
relevante para a Etapa 1 — `fontes_brutas/ibge_municipios_full.csv`, que traz **offline**
a hierarquia geográfica completa dos 5.570+ municípios (UF, micro/meso, regiões
imediata/intermediária). A silvicultura (PEVS) já está parcialmente processada
(`GUIA_PEVS_Silvicultura.md`, scripts entregues).

> Observação: o arquivo `resumo_base_pam_ppm.md` citado no briefing **não foi
> localizado** nem em `pam-dashboard/` nem na raiz de `Base_Municipios_Brasil/`. O
> diagnóstico foi feito a partir do `README.md`, dos scripts do `generator/` e do
> `DICIONARIO_DE_DADOS.md` da base-mestra. Se o resumo existir em outra pasta, basta
> conectá-la para incorporá-lo.

## 2. Tratamento de códigos municipais e limites de requisição

- Código municipal: sempre **texto de 7 dígitos**, começando por 11–53 (UF). A base
  complementar reforça isso em `common.cod_mun7()` — **sem** `zfill` (um "35" de UF
  jamais vira "0000035"); a integridade `cod[:2] == cod_uf` é validada.
- Limites SIDRA já enfrentados: consultas nacionais estouram tempo/500; a mitigação
  adotada (e replicada aqui) é **1 UF por vez** com `pausa` entre requisições, retry
  com backoff, tratamento de `429` (espera) e `400` (recorte sem dado).

## 3. Classificação de cada fonte

| Fonte | Instituição | Situação | Observação |
|---|---|---|---|
| Malha municipal / hierarquia | IBGE Localidades | **Disponível automaticamente** | E também **offline** via `ibge_municipios_full.csv` — usado para gerar `dim_municipio` já nesta sessão. |
| Áreas territoriais (km²) | IBGE Geociências | **Download manual** | Planilha "Áreas dos Municípios"; sem ela, `area_municipal_ha` fica `null` (não zero). |
| Malha municipal (geometrias) | IBGE Malhas v3 | **Disponível automaticamente** | Necessária para interseção do CAR; pesada. |
| Censo Agropecuário 2017 | IBGE/SIDRA | **Disponível automaticamente** (validar tabelas) | Números de tabela **não assumidos**: validados por metadados (`variables.yaml`). |
| PEVS (silvicultura/extração) | IBGE/SIDRA | **Disponível / parcialmente processado** | Reaproveita `download_pevs_ibge.py`. |
| Módulo fiscal | INCRA | **Download manual** | Índices Básicos (IE 20/1980); adaptador local. |
| SNCR (imóveis rurais) | INCRA | **Disponível por UF (manual)** | Download por UF; privacidade obrigatória (sem CPF/CNPJ/nome). |
| CAR | SICAR/SFB | **Disponível com restrições / por UF (manual)** | Termos de uso; UFs podem ter sistema estadual; sem contornar CAPTCHA. |
| MapBiomas | Rede MapBiomas | **Download manual (complementar)** | Estatística municipal em XLSX; raster via GEE. Fonte complementar, citar coleção/versão. |

Legenda usada (conforme briefing): disponível automaticamente; por download manual;
com restrições; apenas por UF; indisponível; necessita validação adicional.

## 4. Restrição de ambiente (decisiva para a execução)

O ambiente Cowford/Cowork em nuvem tem **allowlist de rede fechada**: IBGE, INCRA,
SICAR e MapBiomas **não são alcançáveis** aqui (teste de conectividade retornou HTTP
000 para `servicodados.ibge.gov.br` e `apisidra.ibge.gov.br`). A VM local da ponte
também não tem rede nem `geopandas`/`pyarrow`. Portanto:

- **Os coletores oficiais rodam na SUA máquina** (rede aberta) — exatamente como os
  geradores PAM/PPM/PEVS já fazem.
- Nesta sessão foi possível construir **de verdade e offline** a dimensão territorial
  (`dim_municipio`, 5.571 municípios), porque a hierarquia já estava disponível em
  `ibge_municipios_full.csv`. As demais camadas ficaram com **pipeline pronto +
  adaptador local**, aguardando os brutos oficiais (que só baixam na sua máquina).

Nada foi apresentado como concluído sem ter sido efetivamente processado.

## 5. Reaproveitamento

- `download_pevs.py` **não duplica** o coletor PEVS: localiza o consolidado gerado por
  `generator/download_pevs_ibge.py` e o traz para `data/raw/`.
- `dim_municipio` reaproveita `ibge_municipios_full.csv` (offline) e `estados.csv`.
- Convenções (código como texto, `;`/utf-8, nulos nunca zero, SIDRA por UF) idênticas
  às dos geradores existentes, para integração futura sem atrito.
