# Bases complementares — fundiárias, produtivas e ambientais (Agrocore)

Pipelines para construir bases nacionais complementares ao Dashboard Agrocore (PAM/PPM),
mantidas **separadas** do dashboard em produção até a fase de integração. Cobrem:
estrutura fundiária (SNCR, módulo fiscal), Censo Agropecuário 2017, silvicultura/extração
(PEVS), Cadastro Ambiental Rural (CAR) e uso/cobertura do solo (MapBiomas).

Esta pasta (`generator/complementary/`) **não altera** `public/data/pkg.json`, `ppm.json`,
a interface, o JS do dashboard nem as rotas do Netlify. Tudo é gravado em área separada
(`data/`), fora do que o Netlify publica.

## Estrutura

```
generator/complementary/
  config/     sources.yaml, variables.yaml, area_groups.csv, forestry_groups.csv,
              land_use_classes.csv, car_status_map.csv
  download/   coletores oficiais (rodam na sua máquina) + adaptadores locais
  process/    tratamento e agregação por município
  quality/    controles de qualidade (quality_rules.yaml)
  tests/      pytest
  docs/       esta documentação
  run_pipeline.py
data/
  raw/  interim/  processed/  manifests/
```

## Pré-requisitos

Python 3.11+ e:

```
pip install pandas pyarrow pyyaml requests numpy
# Para a Etapa 2 (CAR / geometrias):
pip install geopandas shapely pyogrio pyproj
# Para ler planilhas (áreas IBGE, MapBiomas):
pip install openpyxl
```

## Onde ficam os brutos

Nos documentos, nos scripts e nas mensagens, `data/raw/...` é a raiz lógica dos brutos.
Nesta máquina ela fica fora da pasta sincronizada, no caminho gravado em
`data/raw_dir.txt` (hoje `D:\00-Claude_Fora_Drive\pam-dashboard\raw`). A variável
`PAM_RAW_DIR` tem prioridade sobre o arquivo, e sem os dois vale `data/raw` dentro do
projeto (`common.RAW_DIR`). Um bruto que parece faltar em `data/raw` deve ser procurado
primeiro ali: é o caso de `ibge/areas_municipios.csv`, que o
`download/download_ibge_areas.py` grava a partir da edição mais recente do IBGE.

## Como rodar

Os **downloads oficiais só funcionam com rede aberta** (na sua máquina). Em ambiente
com allowlist, use `--no-download` para processar apenas o que já estiver em `data/raw`.

```bash
cd pam-dashboard/generator/complementary

# Etapa 1 (fundiária/produtiva)
python run_pipeline.py --stage 1                    # baixa + processa
python run_pipeline.py --stage 1 --no-download      # só processa data/raw

# Etapa 2 (CAR + uso do solo), UF piloto
python run_pipeline.py --stage 2 --uf MT

# Um passo só
python run_pipeline.py --only geography
```

### Ordem interna (seção 13 do briefing)

1. `process_geography` → `dim_municipio` · 2. `process_modulo_fiscal` ·
3. `process_censo_agro` · 4. `process_sncr` · 5. `process_pevs` ·
6. `build_rural_profile` · 7. (Etapa 2) `download_car`/matriz ·
8. `process_car --uf <UF>` · 9. `process_car_estrutura` · 10. `process_mapbiomas` ·
11. `build_rural_profile` de novo.

O `build_rural_profile` grava sempre o stage1 e o stage2, este com o CAR e o MapBiomas
que houver em `data/processed`: o `export_frontend` prefere o stage2.

## Fontes que exigem download manual

Coloque os brutos nestes caminhos e rode o passo correspondente:

- SNCR (INCRA, por UF) → `data/raw/sncr/<uf>/`
- CAR (SICAR, por UF) → `data/raw/car/<uf>/`
- MapBiomas (estatística) → `data/raw/mapbiomas/mapbiomas_cobertura_municipios.xlsx`

Ver `config/sources.yaml` para os portais oficiais e `docs/SOURCES.md`.

## Rastreabilidade

Cada passo grava um manifesto em `data/manifests/<dataset>.json` (fonte, datas,
hashes SHA-256, contagens, avisos). `run_pipeline.py` consolida em
`data/manifests/complementary_data_manifest.json`.

## Privacidade

As bases tratadas **não contêm** CPF, CNPJ de titular, nome de pessoa física,
endereço, telefone ou e-mail. Identificadores públicos de imóvel entram só como
**hash** na camada tratada. Ver `docs/CAR_LIMITATIONS.md` e a seção 2.3 do briefing.

## Testes

```bash
python -m pytest tests/ -q
```
