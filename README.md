# PAM Dashboard — AgroCore

Dashboard dos Dados de Produção Agrícola Municipal com base no estudo do IBGE.
Dados disponíveis dos anos 2004 até 2024.

## Estrutura do Projeto

```
pam-dashboard/
├── generator/
│   ├── process_pam.py      ← gerador de dados (rodar localmente)
│   └── requirements.txt
├── public/                 ← pasta publicada no Netlify
│   ├── index.html
│   ├── css/style.css
│   ├── js/main.js
│   └── data/               ← gerado pelo process_pam.py (não commitado)
│       ├── pkg.json
│       ├── geo_uf.json
│       └── geo_mic.json
├── netlify.toml
└── .gitignore
```

## Pré-requisito

Arquivo CSV do IBGE (PAM):
```
C:\Users\schap\Downloads\IBGE\dados_pam\PAM_municipios_completo.csv
```

## Como Gerar os Dados

```bash
cd pam-dashboard
pip install -r generator/requirements.txt
py generator/process_pam.py
```

Isso cria os 3 arquivos JSON em `public/data/` (pode levar alguns minutos na
primeira execução, pois faz download dos polígonos GeoJSON da API do IBGE).

## Como Publicar no Netlify

1. Gere os dados localmente (passo acima)
2. Faça commit de tudo **incluindo** `public/data/` (o `.gitignore` exclui por
   padrão — remova ou faça `git add -f public/data/` antes do commit)
3. Push para o repositório conectado ao Netlify
4. O Netlify publica a pasta `public/` automaticamente (ver `netlify.toml`)

> **Alternativa:** No Claude Code, rode `git add -f public/data/` para incluir
> os dados no commit, ou ajuste o `.gitignore` para não ignorá-los.

## Tecnologias

- **Leaflet.js** — mapas interativos
- **Chart.js** — gráficos
- **IBGE Malhas API v3** — polígonos GeoJSON de UFs e Microrregiões
- **Netlify** — hospedagem estática
