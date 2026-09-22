# SOURCES — Fontes oficiais e rastreabilidade

Fonte da verdade da identidade territorial: **IBGE**. Prioridade sempre para a fonte
primária oficial; terceiros só como apoio técnico, nunca como substituto silencioso.
Detalhes operacionais em `config/sources.yaml` (campos de rastreabilidade da seção 2.2).

| Camada | Fonte / Instituição | Portal oficial | Formato | Acesso |
|---|---|---|---|---|
| Municípios + hierarquia | IBGE Localidades | servicodados.ibge.gov.br/api/v1/localidades | JSON | automático (e offline via base-mestra) |
| Área territorial (km²) | IBGE Geociências | ibge.gov.br/geociencias → Áreas dos Municípios | XLSX | manual |
| Malha municipal (geom.) | IBGE Malhas v3 | servicodados.ibge.gov.br/api/v3/malhas | GeoJSON/SHP | automático |
| Censo Agropecuário 2017 | IBGE/SIDRA | apisidra.ibge.gov.br + v3/agregados | JSON | automático (tabelas validadas por metadados) |
| PEVS | IBGE/SIDRA | apisidra.ibge.gov.br | JSON | automático (via `download_pevs_ibge.py`) |
| Módulo fiscal | INCRA | gov.br/incra (Índices Básicos, IE 20/1980) | XLSX/CSV | manual |
| SNCR | INCRA | gov.br/incra; acervofundiario.incra.gov.br | CSV/SHP por UF | manual, por UF |
| CAR | SICAR / Serviço Florestal Brasileiro | car.gov.br; consultapublica.car.gov.br | SHP por UF/mun. | manual, com termos de uso |
| Uso e cobertura | MapBiomas | brasil.mapbiomas.org/estatisticas | XLSX / GeoTIFF (GEE) | manual, complementar |

## Registro de extração (o que anotar por arquivo)

Para cada bruto baixado, o manifesto (`data/manifests/*.json`) registra: nome da
fonte, instituição, endpoint/página de origem, data e hora da extração, data de
referência dos dados, formato original, nº de registros, tamanho, **hash SHA-256**,
método de download, filtros aplicados e observações de cobertura/limitação.

## Licenças e termos

- IBGE: dados públicos, citar o IBGE e o ano de referência.
- INCRA/SNCR e SICAR/CAR: dados públicos com **restrições de privacidade** — não
  divulgar titular; ver `CAR_LIMITATIONS.md`. Registrar os termos de uso do SICAR.
- MapBiomas: **CC-BY-SA** — citar coleção e versão; fonte complementar.

## Não fazer

Não usar bases comerciais/terceiros quando a informação estiver na fonte oficial.
Não inventar endpoints. Não contornar CAPTCHA, autenticação ou controles. Onde o
caminho de download não estiver confirmado, `config/sources.yaml` marca `verificar: true`.
