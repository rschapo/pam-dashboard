# Publicação — Silvicultura (PEVS/IBGE) no dashboard AgroCore

> Handoff para conferência no Claude Code. Data: 2026-07-28.
> Repositório: `pam-dashboard` (github.com/rschapo/pam-dashboard) · Deploy: Netlify
> (boisterous-maamoul-a8039b.netlify.app, publica automático a cada push na `main`).

## 1. O que foi feito, em uma frase

Adicionamos a **PEVS — Produção da Extração Vegetal e da Silvicultura** (IBGE) como a
terceira perna do tripé de produção, ao lado do PAM (lavouras) e da PPM (pecuária):
coletamos os dados oficiais por município (2004–2024), geramos o `pevs.json` e
construímos a aba **Silvicultura** no dashboard, além de integrar a camada na base-mestra.

## 2. Estado do Git (já publicado)

- Commit: **`ac49ce8`** — "Adiciona Silvicultura (PEVS/IBGE) como 3o dominio: pevs.json + aba no dashboard + coletor"
- Push: feito na branch **`main`** (houve um `git pull --rebase` sobre um commit remoto novo; sem conflitos).
- Uma alteração não relacionada no `.gitignore` (que já existia na árvore de trabalho) foi
  preservada via stash e devolvida — **não** entrou neste commit.

Conferir:
```bash
git log --oneline -3
git show --stat ac49ce8
```

## 3. Arquivos criados / alterados

### Repositório pam-dashboard (versionados neste commit)
| Arquivo | Mudança |
|---|---|
| `generator/download_pevs_ibge.py` | **novo** — coletor SIDRA das 3 tabelas PEVS (291/289/5930), auto-descobre variáveis/classificação nos metadados, 1 estado×ano por vez, retomável |
| `generator/process_pevs.py` | **novo** — gera `public/data/pevs.json` (molde do `ppm.json`, carga sob demanda) |
| `public/data/pevs.json` | **novo** — 16,3 MB; 27 UF, 556 microrregiões, 5.446 municípios (add com `-f`, pois `public/data/` está no `.gitignore`) |
| `public/index.html` | 3º botão de domínio, filtros e KPIs da silvicultura |
| `public/js/main.js` | domínio "silvicultura" (loadPEVS, switchDomain, calc*, updateKPIsSil, exports, binds) |
| `public/css/style.css` | visibilidade dos 3 domínios + `domain-switch` em 3 colunas |

### Projeto Agrocore (Estudos) — base-mestra (NÃO versionado; fica no seu disco)
Gerados por `Base_Municipios_Brasil/scripts/coletar_base.py --camada silvicultura`:
- `Base_Municipios_Brasil/dados/mun_silvicultura.csv` — 263.832 linhas (produção + valor, tab. 291)
- `Base_Municipios_Brasil/dados/mun_silvicultura_area.csv` — 61.015 linhas (área por espécie, tab. 5930)
- `Base_Municipios_Brasil/dados/mun_extracao_vegetal.csv` — 234.174 linhas (nativa, tab. 289)
- `DICIONARIO_DE_DADOS.md` atualizado (Camada 7) + `GUIA_PEVS_Silvicultura.md`

### Dados brutos da coleta (no seu disco, fora do git)
`data/raw/ibge/pevs/` — 54 arquivos-ano em `raw/` + `PEVS_municipios_completo.csv` (717.165 linhas, 62,5 MB).
Fica dentro do projeto, mas fora do git (`data/raw/` está no `.gitignore`).

## 4. Como conferir a publicação

1. **Deploy do Netlify:** veja no painel do Netlify se o build do commit `ac49ce8` concluiu (verde).
2. Abra o site publicado e dê **hard refresh** (Ctrl+F5) para pegar `main.js` e `pevs.json` novos.
3. **Checklist funcional da aba Silvicultura:**
   - O 3º botão "🌲 Silvicultura" aparece ao lado de Agrícola/Pecuária.
   - Ao clicar, mostra "⏳ Carregando…" (baixa o `pevs.json`) e então troca o domínio.
   - Os "Tipos" funcionam: Silvicultura (plantada) · Extração vegetal (nativa) · Área plantada (espécie).
   - Estado inicial já traz dado real: Silvicultura › "1.1 - Carvão vegetal" › Valor → ~R$ 7,96 bi nacionais em 2024.
   - Métrica muda com o tipo: Silvicultura/Extração = Valor/Quantidade; Área plantada = Área (ha), sem Valor.
   - Mapa do Brasil, Estado/Micro, Municípios, Série Histórica e Rankings reagem ao filtro.
   - Ranking de UF por valor de silvicultura deve destacar **MG, PR, SP, MS, SC, RS, BA, ES** (bate com a realidade).

## 5. Verificações já feitas (antes do push)

- Integridade da coleta: 291 e 289 = 21/21 anos, 5930 = 12/12; nenhum ano vazio/faltante; nº de UFs
  constante por ano (26/24/25) — sinal de coleta completa (falha faria o número oscilar).
- `node --check public/js/main.js` → sintaxe OK.
- IDs do HTML conferidos contra o JS (f-metrica-sil, f-categoria-sil, tipo-sil-btn, kpi-sil-*).
- Contrato de dados do `pevs.json` conferido (chaves `tipos`/`categorias_por_tipo`/`metricas_por_tipo`/
  `est_data`/`mic_data`/`mun_data`/`sep`; chave composta "tipo||categoria").
- **Não** foi possível smoke-test no navegador a partir daqui (o piloto de Chrome disponível é macOS-only;
  a máquina é Windows). A validação foi por contrato de dados + sintaxe + espelho fiel do domínio Pecuária,
  que já roda em produção. → **Vale um olhar visual seu no deploy.**

## 6. Nuances de dados (importante)

- **Hierarquia de produtos (PEVS 291/289):** o IBGE traz os produtos em níveis
  ("1.1 - Carvão vegetal", "1.1.1 - Carvão de eucalipto", "1.3 - Madeira em tora", "1.3.1 - para papel e
  celulose"…). Todos os níveis foram preservados (sem perda). **Somar entre níveis dupla-conta** — agregue
  sempre dentro de um nível. A aba lista todos como categorias selecionáveis.
- **Silvicultura = floresta plantada; Extração vegetal = nativa.** Conceitos distintos, tabelas separadas.
- **Área (tab. 5930)** começa em 2013 (série mais curta); anos anteriores ficam zerados.
- **Unidade:** o SIDRA não retornou coluna de unidade nessas consultas, então `unidades` no `pevs.json`
  está vazio (a quantidade de silvicultura mistura m³ e t conforme o produto). O foco de valor (R$) não é afetado.

## 7. Como regenerar / recoletar (se precisar)

Rodar na sua máquina (o IBGE não é alcançável no ambiente Cowork). Interpretador:
`C:\Users\schap\AppData\Local\Python\pythoncore-3.14-64\python.exe`.
```bash
# 1) coleta (retomável; ~1,5–2 h; roda destacada para não cair com a sessão)
py generator/download_pevs_ibge.py
# 2) json do dashboard
py generator/process_pevs.py         # -> public/data/pevs.json
# 3) camada da base-mestra
cd ../../"Agrocore (Estudos)"/Base_Municipios_Brasil/scripts
py coletar_base.py --camada silvicultura
# 4) publicar
git add -f public/data/pevs.json && git add public/ generator/
git commit -m "..." && git push origin main
```

## 8. Pendências / próximos passos (opcionais)

- Conferência visual do deploy (item 4).
- Se quiser, ajustar a aba para, por padrão, mostrar só produtos de nível-1 (evita a percepção de dupla contagem).
- Explorar/cruzar a silvicultura já integrada à base-mestra (ex.: valor lavoura + floresta plantada por município;
  onde estão os plantios de eucalipto/pinus vs. crédito rural).
