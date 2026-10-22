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
| Módulo fiscal | INCRA | gov.br/incra (Índices Básicos de 2013 e IE nº 5/2022); in.gov.br (IE no DOU) | PDF/XLS/HTML | automático |
| SNCR | INCRA | gov.br/incra; acervofundiario.incra.gov.br | CSV/SHP por UF | manual, por UF |
| CAR | SICAR / Serviço Florestal Brasileiro | car.gov.br; consultapublica.car.gov.br | SHP por UF/mun. | manual, com termos de uso |
| Uso e cobertura | MapBiomas | brasil.mapbiomas.org/estatisticas | XLSX / GeoTIFF (GEE) | manual, complementar |
| Produtores: estabelecimentos por atividade e tipologia | IBGE, Censo Agropecuário 2017 | SIDRA 6778, resposta bruta com os símbolos (`download_censo_estabelecimentos.py`, 22/10/2026) | JSON | automático |
| Contas-chave e produtores rurais | Receita Federal, Dados Abertos CNPJ | arquivos.receitafederal.gov.br (base local `cnpj_<período>.duckdb` da pasta Dados Receita Federal; em uso, 2026-10, aberturas até 11/10/2026) | CSV → DuckDB | automático (scripts da pasta Dados Receita Federal) |
| Usinas (validação) | ANP, Painel Dinâmico de Produtores de Etanol | gov.br/anp/.../arquivos-etanol/pb-da-etanol.zip (baixado em 21/10/2026, sha256 30f9150a722e1f21e7d4aa7d38be6fcb9950ece87bca5531b29154d9122c9010; último mês 09/2026) | ZIP/CSV | automático (`download_anp_etanol.py`) |

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
- Receita Federal (CNPJ) e ANP: dados públicos. No painel, só contagens por município: não
  publicar sócios (QSA) nem dado de pessoa física (nome, CPF/CNPJ de pessoa física, endereço,
  contato, coordenada, data de abertura individual). Regra completa em
  `RECEITA_CONTAS_E_PRODUTORES.md`.

## Não fazer

Não usar bases comerciais/terceiros quando a informação estiver na fonte oficial.
Não inventar endpoints. Não contornar CAPTCHA, autenticação ou controles. Onde o
caminho de download não estiver confirmado, `config/sources.yaml` marca `verificar: true`.
