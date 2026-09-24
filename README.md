# PAM Dashboard — AgroCore

Dashboard dos Dados de Produção Agrícola Municipal com base no estudo do IBGE.
Lavouras (PAM) e silvicultura/extração vegetal (PEVS) de 2004 a 2025; pecuária (PPM)
de 2004 a 2024, porque a PPM 2025 ainda não foi publicada. O seletor de ano segue a PAM, e
o domínio que não tem o ano escolhido mostra o último que publicou, com aviso.

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
<brutos>/ibge/pam/PAM_municipios_completo.csv
```
Os brutos ficam fora da pasta sincronizada: `<brutos>` é o caminho em
`data/raw_dir.txt` (ou na variável `PAM_RAW_DIR`); sem nenhum dos dois, `data/raw`.
Todos os coletores e processadores (PAM, PPM, PEVS e o pipeline complementar) usam
essa mesma regra.

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
