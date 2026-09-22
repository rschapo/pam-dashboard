# INTEGRATION_PLAN — Plano de integração futura (proposta, não executar agora)

Como as bases complementares poderão, na **fase posterior**, alimentar o dashboard sem
alterar `pkg.json`/`ppm.json` nem a interface. Nada aqui é executado nesta entrega.

## Princípios

- Manter o padrão do front-end: identificação por `cod_municipio` (7 díg, texto),
  `cod_microrregiao`, `UF`, `ano`; arquivos JSON independentes carregados **sob demanda**
  (como `ppm.json`/`pevs.json` já são); séries 2004–2024 quando aplicável.
- Cada nova aba/camada = **um JSON próprio**, gerado a partir dos Parquet de
  `data/processed/`, espelhando a estrutura `est_data`/`mic_data`/`mun_data`.

## Artefatos-alvo do front-end

| JSON | Origem (processed/) | Conteúdo |
|---|---|---|
| `perfil_rural.json` | `rural_profile_stage1/2` | Perfil fundiário/produtivo por município |
| `pevs.json` | `pevs_municipio` | Já existe; manter o gerador atual |
| `car_profile.json` | `car_municipio_summary` | Resumo do CAR por município (agregado) |
| `land_use.json` | `mapbiomas_municipio` | Uso e cobertura por município/ano |

## Dimensionamento e desempenho

- **Tamanho estimado**: `perfil_rural` e `car_profile` são pequenos (uma linha por
  município → ~1–3 MB por JSON compacto). `land_use.json` é o maior (município × classe
  × ano); mitigar com **agregação por grupo analítico** e/ou **partição por UF**
  (`land_use_<uf>.json`), carregando só a UF selecionada.
- **Carregamento sob demanda**: cada aba busca seu JSON só ao abrir, como o `ppm.json`.
- **Compressão**: JSON compacto (`separators=(',',':')`) + gzip do Netlify. Onde o
  volume crescer, considerar **Parquet + DuckDB-WASM** no cliente para consulta local
  sem baixar tudo.
- **Netlify**: publicação estática — sem backend obrigatório. Um backend só seria
  necessário para consultas geoespaciais interativas pesadas (recorte por imóvel), que
  ficam fora do dashboard (processadas offline, servidas já agregadas).

## Riscos e cuidados

- **Não** cruzar CAR/SNCR/Censo com PAM/PPM antes desta fase; a junção final valida
  chaves e anos de referência distintos.
- Geometrias completas do CAR **não** vão ao front-end (peso e privacidade); só
  agregados municipais. Mapas usam a malha já existente colorida por indicador.
- Séries com anos de referência diferentes (Censo 2017, PEVS anual, CAR dinâmico,
  MapBiomas por coleção) exigem rótulo de ano explícito em cada camada.

## Implementação já disponível (offline)

O exportador da **Etapa 3** já existe: `process/export_frontend.py` gera
`data/frontend/perfil_rural.json` (e `car_profile.json`/`land_use.json` quando as
camadas existirem) — pasta **separada** de `public/data/`, sem tocar na produção.
O protótipo da **Etapa 4** (`process/build_preview.py`) gera
`preview/perfil_rural_preview.html`, autocontido (abre por duplo-clique), para
visualizar a base antes da integração. Rode ambos com `run_pipeline.py --stage 3`.
Hoje o `perfil_rural.json` já traz identidade + `tem_pam`/`tem_ppm` dos 5.571
municípios; os campos fundiários/ambientais preenchem conforme as camadas 1–2 forem
processadas. A integração definitiva ao dashboard (novas abas em `public/`) continua
para a fase posterior — este protótipo é o ensaio, não a produção.

## Sequência sugerida da integração (fase posterior)

1. Gerar `perfil_rural.json` de `rural_profile_stage2` e adicionar aba "Perfil rural".
2. `car_profile.json` + aba CAR (com os avisos de `CAR_LIMITATIONS.md` na UI).
3. `land_use.json` particionado por UF + aba Uso do solo.
4. Só então avaliar cruzamentos PAM/PPM × fundiário/ambiental como indicadores derivados.
