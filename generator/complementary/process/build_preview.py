"""
build_preview.py — Etapa 4: protótipo de aba (preview) das bases complementares.

Gera um HTML AUTOCONTIDO em generator/complementary/preview/perfil_rural_preview.html
com o perfil_rural embutido (abre por duplo-clique, sem servidor). É um PROTÓTIPO
SEPARADO da produção — não toca em public/index.html, public/js/main.js, pkg.json
nem ppm.json. Serve para visualizar a base complementar antes da integração real.

Uso:
  python build_preview.py     (depois de export_frontend.py)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import DATA_DIR  # noqa: E402

PREVIEW_DIR = Path(__file__).resolve().parents[1] / "preview"
PERFIL = DATA_DIR / "frontend" / "perfil_rural.json"

TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agrocore — Perfil Rural (protótipo)</title>
<style>
:root{--bg:#0f1419;--card:#1a2028;--ink:#e6edf3;--mut:#8b98a5;--line:#2a323c;--acc:#4a9d5b;--warn:#c9a227}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.5 system-ui,Segoe UI,Roboto,sans-serif}
header{padding:20px 24px;border-bottom:1px solid var(--line)}
h1{margin:0 0 4px;font-size:18px}.sub{color:var(--mut);font-size:13px}
.wrap{padding:20px 24px;max-width:1100px;margin:0 auto}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
.card .n{font-size:22px;font-weight:600}.card .l{color:var(--mut);font-size:12px;margin-top:2px}
.bar{height:6px;border-radius:4px;background:var(--line);margin-top:8px;overflow:hidden}
.bar>span{display:block;height:100%;background:var(--acc)}
.controls{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}
input,select{background:var(--card);color:var(--ink);border:1px solid var(--line);
border-radius:8px;padding:8px 10px;font-size:14px}
input{flex:1;min-width:200px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}
th{color:var(--mut);font-weight:600;position:sticky;top:0;background:var(--bg)}
.tag{display:inline-block;padding:1px 7px;border-radius:20px;font-size:11px}
.yes{background:rgba(74,157,91,.2);color:#7fd396}.no{background:rgba(201,162,39,.18);color:#e0c25a}
.muted{color:var(--mut)}.count{color:var(--mut);font-size:12px;margin:8px 0}
footer{padding:16px 24px;color:var(--mut);font-size:12px;border-top:1px solid var(--line)}
</style></head><body>
<header><h1>Perfil Rural — bases complementares (protótipo)</h1>
<div class="sub">Protótipo de aba · dados de <code>data/frontend/perfil_rural.json</code> · NÃO altera o dashboard em produção</div></header>
<div class="wrap">
<div class="cards" id="cards"></div>
<div class="controls">
<input id="q" placeholder="Buscar município ou código IBGE…">
<select id="uf"><option value="">Todas as UFs</option></select>
<select id="filtro">
<option value="">Todos</option>
<option value="pam0">Sem PAM</option>
<option value="ppm0">Sem PPM</option>
</select>
</div>
<div class="count" id="count"></div>
<table><thead><tr><th>Código</th><th>Município</th><th>UF</th><th>Região</th>
<th>Área (ha)</th><th>PAM</th><th>PPM</th></tr></thead>
<tbody id="tb"></tbody></table>
</div>
<footer>Agrocore · gerado por build_preview.py · Etapa 4 (protótipo). Campos fundiários/ambientais
preenchem conforme as camadas forem processadas na sua máquina.</footer>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const MUN = D.mun, LIMIT = 400;
const fmt = v => v==null ? '<span class="muted">—</span>' : (typeof v==='number'? v.toLocaleString('pt-BR'):v);
const tag = v => v==null? '<span class="muted">—</span>' : (v? '<span class="tag yes">sim</span>':'<span class="tag no">não</span>');
// cards de cobertura
const cov = D.cobertura, tot = D.n_municipios;
const cardDefs = [['n_municipios','Municípios',tot],
  ['tem_pam','Com PAM',Object.values(MUN).filter(m=>m.tem_pam).length],
  ['tem_ppm','Com PPM',Object.values(MUN).filter(m=>m.tem_ppm).length],
  ['area_municipal_ha','Com área (ha)',cov.area_municipal_ha||0]];
document.getElementById('cards').innerHTML = cardDefs.map(([k,l,n])=>{
  const pct = Math.round(100*n/tot);
  return `<div class="card"><div class="n">${n.toLocaleString('pt-BR')}</div>
  <div class="l">${l} · ${pct}%</div><div class="bar"><span style="width:${pct}%"></span></div></div>`;
}).join('');
// UF options
Object.keys(D.ufs_info).sort().forEach(uf=>{
  const o=document.createElement('option');o.value=uf;o.textContent=uf+' — '+D.ufs_info[uf];
  document.getElementById('uf').appendChild(o);});
const q=document.getElementById('q'),uf=document.getElementById('uf'),
  filtro=document.getElementById('filtro'),tb=document.getElementById('tb'),cnt=document.getElementById('count');
function render(){
  const term=q.value.trim().toLowerCase(), fUf=uf.value, f=filtro.value;
  let rows=[], n=0;
  for(const cod in MUN){const m=MUN[cod];
    if(fUf && m.uf!==fUf) continue;
    if(f==='pam0' && m.tem_pam!==false) continue;
    if(f==='ppm0' && m.tem_ppm!==false) continue;
    if(term && !(cod.includes(term) || (m.nome_municipio||'').toLowerCase().includes(term))) continue;
    n++; if(rows.length<LIMIT) rows.push([cod,m]);
  }
  cnt.textContent = n.toLocaleString('pt-BR')+' município(s)'+(n>LIMIT?` (mostrando ${LIMIT})`:'');
  tb.innerHTML = rows.map(([cod,m])=>`<tr><td>${cod}</td><td>${m.nome_municipio||''}</td>
    <td>${m.uf||''}</td><td>${m.nome_regiao||''}</td><td>${fmt(m.area_municipal_ha)}</td>
    <td>${tag(m.tem_pam)}</td><td>${tag(m.tem_ppm)}</td></tr>`).join('');
}
[q,uf,filtro].forEach(e=>e.addEventListener('input',render)); render();
</script></body></html>
"""


def main():
    if not PERFIL.exists():
        raise SystemExit("perfil_rural.json ausente. Rode export_frontend.py primeiro.")
    data = PERFIL.read_text(encoding="utf-8")
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    html = TEMPLATE.replace("__DATA__", data)
    out = PREVIEW_DIR / "perfil_rural_preview.html"
    out.write_text(html, encoding="utf-8")
    mb = out.stat().st_size / 1_048_576
    print(f"[PREVIEW] {out} · {mb:.2f} MB (abre por duplo-clique)")


if __name__ == "__main__":
    main()
