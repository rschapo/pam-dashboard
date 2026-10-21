# CHANGELOG — PAM-dashboard

## 2026-10-21 · branch `painel-brasil-regras-2026-10` (não publicado)

Painel do Brasil, sem concessionário: densidades, cultura dominante, contas-chave e
produtores rurais agregados.

**Novo**
- Agrícola: métricas Densidade (ha/km²), Vocação (% da área colhida) e Cultura dominante
  (mapa por categoria, resumo com mapa estático em SVG e tabela, no Mapa Brasil e em
  Estado / Micro).
- Agrícola: 14 atalhos de densidade pronta no último ano do PAM (cana, citros, café, floresta
  plantada da PEVS, H&F, H&F sem citros, soja, milho, algodão, arroz, trigo, fumo, tratores e
  colheitadeiras). Arroz, trigo e fumo entraram pelo foco no RS.
- Camada de contas-chave da Receita (usinas validadas pela ANP, sucos, pós-colheita, café,
  florestal, cooperativas): círculos por município e colunas na tabela de municípios. Só
  pessoa jurídica, só contagens.
- Domínio 👨‍🌾 Produtores: cadastros ativos da Receita por município, atividade e tipo (só
  contagens, opção A da regra de dados pessoais), por mil ha colhidos e por km². Abre em
  pessoa jurídica, porque o produtor pessoa física só tem CNPJ em SP e AL.
- Mapas de Estado / Micro e de Municípios com legenda; leituras novas em classes por quantis
  só dos territórios com valor, ausente em cinza.
- Testes de não-identificação de `public/`, das regras do mapa (em node), dos grupos e da
  consistência PAM município × estado.

**Corrigido**
- Café contado duas vezes nos agregados desde 2012 (+1,94 Mha de área colhida em 2025).
- Com uma cultura escolhida, município e microrregião mostravam o total do grupo.
- Legenda do mapa Brasil com faixas lineares para cores em escala logarítmica.
- KPI "Culturas" contava pares estado × cultura.
- Todos os exports gravam JSON com `allow_nan=False`.

Detalhes e números: `generator/complementary/docs/QUALITY_REPORT.md`.
