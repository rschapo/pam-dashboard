/* ============================================================
   AgroCore PAM Dashboard — main.js
   All chart / map logic. Called by index.html after JSON loads.
   ============================================================ */

// AgroCore brand palette
const BRAND_GOLD       = '#C9960C';
const BRAND_GREEN      = '#2D5A1B';
const BRAND_GREEN_LT   = '#3D7526';
const BRAND_GREEN_MID  = '#4A7A35';

// Brasil map: YlOrRd — 7 steps
const COLORS_BR  = ['#ffffb2','#fed976','#feb24c','#fd8d3c','#fc4e2a','#e31a1c','#800026'];
// Micro/estado: warm OrRd — no near-white
const COLORS_MIC = ['#fdd49e','#fdbb84','#fc8d59','#ef6548','#d7301f','#b30000','#7f0000'];

// Chart.js default overrides (green‑brand)
Chart.defaults.font.family = "'Segoe UI', 'Inter', system-ui, sans-serif";
Chart.defaults.font.size   = 12;
Chart.defaults.color       = '#6B7C64';

// ─── Module-level variables ───────────────────────────────────────────────
let PKG, GEO_UF, GEO_MIC;
let anos, culturas, colheitadeiras, tratores, permanentes, temporarias;
let ufs_info, mic_info, mun_info, est_data, mic_data, mun_data, mun_grp_data;
let N_ANOS;

// PPM (Pecuária) — carregado sob demanda na primeira troca para o domínio Pecuária
let PPM = null, ppmLoaded = false, ppmLoading = false;
let rebanho_categorias, producao_categorias, ppm_est_data, ppm_mic_data, ppm_mun_data;

// Unidade de cada categoria pecuária (rebanho = sempre cabeças; produção varia)
const PEC_UNITS = {
  'Bovino': 'cab.', 'Bubalino': 'cab.', 'Caprino': 'cab.', 'Codornas': 'cab.', 'Equino': 'cab.',
  'Galináceos - galinhas': 'cab.', 'Galináceos - total': 'cab.', 'Ovino': 'cab.',
  'Suíno - matrizes de suínos': 'cab.', 'Suíno - total': 'cab.',
  'Leite': 'mil L', 'Ovos de galinha': 'mil dz', 'Ovos de codorna': 'mil dz',
  'Mel de abelha': 'kg', 'Casulos do bicho-da-seda': 'kg', 'Lã': 'kg'
};

let state = {
  tab: 'brasil', domain: 'agricola',
  metricaAgro: 'p', grupoId: 'ALL', cultura: '',
  metricaPec: 'q', tipoPec: 'Rebanho', categoriaPec: '',
  ufSel: '', microSel: '', munSel: '', anoIdx: 0
};

function curMetrica() { return state.domain === 'pecuaria' ? state.metricaPec : state.metricaAgro; }
function getActiveCategoriasPec() { return state.tipoPec === 'Rebanho' ? rebanho_categorias : producao_categorias; }

// ═══════════════════════════════════════════════════════════
// ENTRY POINT — called from index.html after fetch()
// ═══════════════════════════════════════════════════════════
window.initDashboard = function(pkg, geoUF, geoMic) {
  PKG      = pkg;
  GEO_UF   = geoUF;
  GEO_MIC  = geoMic;

  ({ anos, culturas, colheitadeiras, tratores, permanentes, temporarias,
     ufs_info, mic_info, mun_info, est_data, mic_data, mun_data, mun_grp_data } = PKG);

  N_ANOS = anos.length;
  state.anoIdx = N_ANOS - 1;

  // Update header badge
  const badge = document.getElementById('hdr-anos-badge');
  if (badge) badge.textContent = anos[0] + '–' + anos[N_ANOS - 1];

  // Update ano slider range
  const slider = document.getElementById('f-ano');
  if (slider) { slider.max = N_ANOS - 1; slider.value = N_ANOS - 1; }

  document.body.dataset.tab = state.tab;
  document.body.dataset.domain = state.domain;
  populateEstados();
  populateCulturas();
  populateMicros();
  populateMunicipios();
  populateMetricaPecOptions();
  initMapBR();
  initMapEst();
  initMapMun();
  bindEvents();
  refreshAll();
};

// ═══════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════
function getAnoIdx() { return state.anoIdx; }
function getAno()    { return anos[state.anoIdx]; }

function getActiveCulturas() {
  if (state.cultura) return [state.cultura];
  if (state.grupoId === 'COL') return colheitadeiras;
  if (state.grupoId === 'TRA') return tratores;
  if (state.grupoId === 'TEM') return temporarias;
  if (state.grupoId === 'PER') return permanentes;
  return culturas;
}

function getMicKey() {
  if (state.cultura && colheitadeiras.includes(state.cultura)) return state.cultura;
  return state.grupoId === 'COL' ? 'COL' : state.grupoId; // ALL, TEM, PER, COL
}

function calcEst(uf, m) {
  if (state.domain === 'pecuaria') {
    const d = ppm_est_data?.[uf]?.[state.categoriaPec]; if (!d) return 0;
    return d[m]?.[getAnoIdx()] || 0;
  }
  const d = est_data[uf]; if (!d) return 0;
  const ai = getAnoIdx();
  return getActiveCulturas().reduce((s, c) => s + (d[c]?.[m]?.[ai] || 0), 0);
}

function calcMic(mid, m) {
  if (state.domain === 'pecuaria') {
    const d = ppm_mic_data?.[mid]?.[state.categoriaPec]; if (!d) return 0;
    return d[m]?.[getAnoIdx()] || 0;
  }
  const key = getMicKey();
  const d = mic_data[mid]; if (!d) return 0;
  return d[key]?.[m]?.[getAnoIdx()] || 0;
}

function calcMunVal(munId, m, ai) {
  if (state.domain === 'pecuaria') {
    const d = ppm_mun_data?.[munId]?.[state.categoriaPec]; if (!d) return 0;
    return d[m]?.[ai] || 0;
  }
  if (state.grupoId && state.grupoId !== 'ALL') {
    const grp = state.grupoId;
    const gd = mun_grp_data[grp];
    if (gd) return gd[munId]?.[m]?.[ai] || 0;
  }
  return mun_data[munId]?.[m]?.[ai] || 0;
}

function metLabel() {
  const M = curMetrica();
  if (state.domain === 'pecuaria') {
    const cat = state.categoriaPec, unit = PEC_UNITS[cat] || '';
    if (!cat) return 'Selecione uma categoria';
    if (M === 'v') return cat + ' — Valor (mil R$)';
    return cat + ' — ' + (state.tipoPec === 'Rebanho' ? 'Efetivo' : 'Quantidade') + (unit ? ' (' + unit + ')' : '');
  }
  if (M === 'p') return 'Produção (ton)';
  if (M === 'a') return 'Área Colhida (ha)';
  if (M === 'v') return 'Valor (mil R$)';
  return 'Rendimento (kg/ha)';
}

function fmt(v, m) {
  if (!v || v === 0) return '—';
  if (m === 'r') return v.toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + ' kg/ha';
  if (v >= 1e9) return (v / 1e9).toLocaleString('pt-BR', { maximumFractionDigits: 2 }) + ' Gi';
  if (v >= 1e6) return (v / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 2 }) + ' Mi';
  if (v >= 1e3) return (v / 1e3).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + ' mil';
  return v.toLocaleString('pt-BR', { maximumFractionDigits: 1 });
}

// ═══════════════════════════════════════════════════════════
// COLOR
// ═══════════════════════════════════════════════════════════
function getColor(v, max, palette) {
  palette = palette || COLORS_BR;
  if (!v || !max) return palette[0];
  const t = Math.min(Math.log1p(v) / Math.log1p(max), 1);
  const i = Math.floor(t * (palette.length - 1));
  return palette[Math.min(i, palette.length - 1)];
}

// ═══════════════════════════════════════════════════════════
// MAP — BRASIL
// ═══════════════════════════════════════════════════════════
let mapBR = null, layerUF = null;

function initMapBR() {
  mapBR = L.map('map-br', { zoomSnap: .5, attributionControl: false });
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', { maxZoom: 12 }).addTo(mapBR);
  updateMapBR();
  mapBR.fitBounds([[-34, -74], [6, -28]]);
}

function updateMapBR() {
  if (!mapBR) return;
  const M = curMetrica();
  const vals = {};
  Object.keys(ufs_info).forEach(uf => { vals[uf] = calcEst(uf, M); });
  const max = Math.max(...Object.values(vals), 1);

  if (layerUF) layerUF.remove();
  layerUF = L.geoJSON(GEO_UF, {
    style(f) {
      const uf = f.properties.uf, v = vals[uf] || 0;
      return { fillColor: getColor(v, max, COLORS_BR), fillOpacity: .78, color: '#fff', weight: 1 };
    },
    onEachFeature(f, layer) {
      const uf = f.properties.uf, v = vals[uf] || 0;
      layer.bindTooltip(
        `<b style="color:${BRAND_GREEN}">${ufs_info[uf]?.n || uf}</b><br>${metLabel()}: <b>${fmt(v, M)}</b>`,
        { sticky: true }
      );
      layer.on('click', () => selectEstado(uf));
    }
  }).addTo(mapBR);

  // Legend
  const existing = document.querySelector('.map-legend-ctrl');
  if (existing) existing.remove();
  const leg = L.control({ position: 'bottomright' });
  leg.onAdd = () => {
    const d = L.DomUtil.create('div', 'map-legend map-legend-ctrl');
    const steps = COLORS_BR.map((_, i) => max * i / (COLORS_BR.length - 1));
    d.innerHTML = `<b>${metLabel()}</b>` +
      COLORS_BR.map((c, i) =>
        `<br><span class="leg-swatch" style="background:${c}"></span>${fmt(steps[i] || 0, M)}`
      ).join('');
    return d;
  };
  leg.addTo(mapBR);
}

// ═══════════════════════════════════════════════════════════
// MAP — ESTADO / MICRO
// ═══════════════════════════════════════════════════════════
let mapEst = null, layerMic = null;
let mapMun = null, layerMunMic = null;

function initMapEst() {
  mapEst = L.map('map-est', { zoomSnap: .5, attributionControl: false });
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', { maxZoom: 14 }).addTo(mapEst);
  mapEst.fitBounds([[-34, -74], [6, -28]]);
}

function updateMapEst() {
  if (!mapEst) return;
  const M = curMetrica(), uf = state.ufSel;
  const mids = Object.keys(mic_info).filter(m => !uf || mic_info[m].uf === uf);
  const vals = {};
  mids.forEach(m => { vals[m] = calcMic(m, M); });
  const max = Math.max(...Object.values(vals), 1);

  const filtered = GEO_MIC.features.filter(f => mids.includes(f.properties.mid));
  if (!filtered.length) return;

  if (layerMic) layerMic.remove();
  layerMic = L.geoJSON({ type: 'FeatureCollection', features: filtered }, {
    style(f) {
      const v = vals[f.properties.mid] || 0;
      return { fillColor: getColor(v, max, COLORS_MIC), fillOpacity: .78, color: '#fff', weight: .8 };
    },
    onEachFeature(f, layer) {
      const mid = f.properties.mid, v = vals[mid] || 0;
      layer.bindTooltip(
        `<b style="color:${BRAND_GREEN}">${mic_info[mid]?.n || mid}</b><br>${metLabel()}: <b>${fmt(v, M)}</b>`,
        { sticky: true }
      );
      layer.on('click', () => selectMicro(mid));
    }
  }).addTo(mapEst);
  mapEst.fitBounds(layerMic.getBounds(), { padding: [10, 10] });

  const nm = uf ? (ufs_info[uf]?.n || uf) : 'Brasil';
  document.getElementById('est-label').textContent = nm + ' — ' + mids.length + ' microrregiões';
  updateChartEst(vals, max, M);
}

function initMapMun() {
  mapMun = L.map('map-mun', { zoomSnap: .5, attributionControl: false });
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', { maxZoom: 14 }).addTo(mapMun);
  mapMun.fitBounds([[-34, -74], [6, -28]]);
}

function updateMapMun() {
  if (!mapMun) return;
  const M = curMetrica(), uf = state.ufSel;
  if (!uf) {
    document.getElementById('mun-map-title').textContent = '🗺️ Mapa do Estado';
    return;
  }
  const mids = Object.keys(mic_info).filter(m => mic_info[m].uf === uf);
  const vals = {};
  mids.forEach(m => { vals[m] = calcMic(m, M); });
  const max = Math.max(...Object.values(vals), 1);
  const filtered = GEO_MIC.features.filter(f => mids.includes(f.properties.mid));
  if (!filtered.length) return;
  if (layerMunMic) layerMunMic.remove();
  layerMunMic = L.geoJSON({ type: 'FeatureCollection', features: filtered }, {
    style(f) {
      const v = vals[f.properties.mid] || 0;
      return { fillColor: getColor(v, max, COLORS_MIC), fillOpacity: .78, color: '#fff', weight: .8 };
    },
    onEachFeature(f, layer) {
      const mid = f.properties.mid, v = vals[mid] || 0;
      layer.bindTooltip(
        `<b style="color:${BRAND_GREEN}">${mic_info[mid]?.n || mid}</b><br>${metLabel()}: <b>${fmt(v, M)}</b>`,
        { sticky: true }
      );
      layer.on('click', () => { state.microSel = mid; updateMunicipio(); });
    }
  }).addTo(mapMun);
  mapMun.fitBounds(layerMunMic.getBounds(), { padding: [10, 10] });
  document.getElementById('mun-map-title').textContent = '🗺️ Microrregiões — ' + (ufs_info[uf]?.n || uf);
}

// ═══════════════════════════════════════════════════════════
// CHARTS — Estado & Micro histórico
// ═══════════════════════════════════════════════════════════
let chEst = null, chMicro = null;

function updateChartEst(vals, max, M) {
  const ctx = document.getElementById('chart-est')?.getContext('2d'); if (!ctx) return;
  const sorted = Object.entries(vals).sort((a, b) => b[1] - a[1]).slice(0, 15);
  if (chEst) chEst.destroy();
  chEst = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: sorted.map(([mid]) => mic_info[mid]?.n || mid),
      datasets: [{ data: sorted.map(([, v]) => v), backgroundColor: BRAND_GREEN_LT, borderRadius: 4 }]
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => fmt(c.raw, M) } } },
      scales: {
        x: { ticks: { callback: v => fmt(v, M) }, grid: { color: '#f0f0f0' } },
        y: { ticks: { font: { size: 10 } } }
      }
    }
  });
  document.getElementById('chart-est-title').textContent = '📊 Top Microrregiões — ' + metLabel();
}

function updateChartMicro() {
  const ctx = document.getElementById('chart-micro')?.getContext('2d'); if (!ctx) return;
  const mid = state.microSel, M = curMetrica();
  if (!mid) { if (chMicro) { chMicro.destroy(); chMicro = null; } return; }
  const series = anos.map((_, ai) => {
    const tmp = state.anoIdx; state.anoIdx = ai;
    const v = calcMic(mid, M); state.anoIdx = tmp; return v;
  });
  if (chMicro) chMicro.destroy();
  chMicro = new Chart(ctx, {
    type: 'line',
    data: {
      labels: anos,
      datasets: [{
        label: mic_info[mid]?.n || mid,
        data: series,
        borderColor: BRAND_GOLD, backgroundColor: 'rgba(201,150,12,.12)',
        fill: true, tension: .35, pointRadius: 3,
        pointBackgroundColor: BRAND_GOLD
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => fmt(c.raw, M) } } },
      scales: {
        x: { grid: { color: '#f0f0f0' } },
        y: { ticks: { callback: v => fmt(v, M) }, grid: { color: '#f0f0f0' } }
      }
    }
  });
  document.getElementById('chart-micro-title').textContent =
    '📈 ' + (mic_info[mid]?.n || mid) + ' — série histórica';
}

// ═══════════════════════════════════════════════════════════
// TAB MUNICÍPIO
// ═══════════════════════════════════════════════════════════
let chMunTop = null, chMunHist = null;

function populateMunicipios() {
  const sel = document.getElementById('f-municipio'); if (!sel) return;
  const uf = state.ufSel;
  if (!uf) { sel.innerHTML = '<option value="">Todos os municípios</option>'; return; }
  const muns = Object.entries(mun_info)
    .filter(([, i]) => i.uf === uf)
    .sort(([, a], [, b]) => a.n.localeCompare(b.n, 'pt-BR'));
  sel.innerHTML = '<option value="">Todos os municípios</option>' +
    muns.map(([id, i]) => `<option value="${id}">${i.n}</option>`).join('');
  sel.value = state.munSel || '';
}

function updateMunicipio() {
  const M = curMetrica(), ai = getAnoIdx(), uf = state.ufSel;
  const hint     = document.getElementById('mun-hint');
  const tbl      = document.getElementById('table-mun');
  const tblTitle = document.getElementById('mun-tbl-title');

  updateMapMun();

  if (!uf) {
    if (hint) hint.textContent = 'Selecione um estado no filtro à esquerda';
    if (tbl) tbl.innerHTML = '<thead><tr><th>#</th><th>Município</th><th>Microrregião</th><th>' + metLabel() + '</th></tr></thead><tbody><tr><td colspan="4" style="text-align:center;padding:24px;color:var(--text-lt)">Selecione um estado</td></tr></tbody>';
    if (chMunTop)  { chMunTop.destroy();  chMunTop  = null; }
    if (chMunHist) { chMunHist.destroy(); chMunHist = null; }
    return;
  }

  const muns = Object.entries(mun_info)
    .filter(([, i]) => i.uf === uf)
    .map(([id, i]) => ({ id, n: i.n, mid: i.mid, v: calcMunVal(id, M, ai) }))
    .filter(x => x.v > 0)
    .sort((a, b) => b.v - a.v);

  const ufName = ufs_info[uf]?.n || uf;
  if (hint) hint.textContent = `${ufName} — ${muns.length} municípios com dados em ${getAno()}`;
  if (tblTitle) tblTitle.textContent = `🏆 Ranking — ${ufName} (${getAno()})`;

  if (tbl) {
    const hdr = `<thead><tr><th>#</th><th>Município</th><th>Microrregião</th><th>${metLabel()}</th></tr></thead>`;
    const rows = muns.slice(0, 100).map((m, i) => {
      const micN = mic_info[m.mid]?.n || '';
      const sel  = m.id === state.munSel ? ' selected-row' : '';
      return `<tr class="${sel}" onclick="toggleMunicipio('${m.id}')" style="cursor:pointer">
        <td class="rank-pos">${i + 1}</td>
        <td><b>${m.n}</b></td>
        <td style="font-size:11px;color:var(--text-lt)">${micN}</td>
        <td class="num">${fmt(m.v, M)}</td>
      </tr>`;
    }).join('');
    tbl.innerHTML = hdr + '<tbody>' + rows + '</tbody>';
  }

  const topEl = document.getElementById('mun-chart-top-title');
  if (topEl) topEl.textContent = `📊 Top 15 Municípios — ${ufName} (${getAno()})`;
  updateMunChartTop(muns.slice(0, 15));

  const histEl = document.getElementById('mun-chart-hist-title');
  if (state.munSel && hasMunData(state.munSel)) {
    if (histEl) histEl.textContent = '📈 Série Histórica — ' + (mun_info[state.munSel]?.n || state.munSel);
    updateMunChartHist(state.munSel);
  } else {
    if (histEl) histEl.textContent = '📈 Série Histórica — ' + ufName;
    updateMunChartHistUF(uf, M);
  }
}

function toggleMunicipio(id) {
  state.munSel = (state.munSel === id) ? '' : id;
  const sel = document.getElementById('f-municipio');
  if (sel) sel.value = state.munSel;
  updateMunicipio();
}

function updateMunChartTop(muns) {
  const ctx = document.getElementById('chart-mun-top')?.getContext('2d'); if (!ctx) return;
  const M = curMetrica();
  if (chMunTop) chMunTop.destroy();
  chMunTop = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: muns.map(m => m.n),
      datasets: [{ label: metLabel(), data: muns.map(m => m.v), backgroundColor: BRAND_GREEN, borderRadius: 4 }]
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => fmt(c.raw, M) } } },
      scales: {
        x: { ticks: { callback: v => fmt(v, M) }, grid: { color: '#f0f0f0' } },
        y: { ticks: { font: { size: 10 } } }
      }
    }
  });
}

function hasMunData(munId) {
  if (state.domain === 'pecuaria') return !!ppm_mun_data?.[munId]?.[state.categoriaPec];
  return !!mun_data[munId];
}

function updateMunChartHist(munId) {
  const ctx = document.getElementById('chart-mun-hist')?.getContext('2d'); if (!ctx) return;
  const M = curMetrica();
  const series = anos.map((_, ai) => calcMunVal(munId, M, ai));
  if (chMunHist) chMunHist.destroy();
  chMunHist = new Chart(ctx, {
    type: 'line',
    data: {
      labels: anos,
      datasets: [{
        label: mun_info[munId]?.n || munId,
        data: series,
        borderColor: BRAND_GOLD, backgroundColor: 'rgba(201,150,12,.12)',
        fill: true, tension: .35, pointRadius: 3, pointBackgroundColor: BRAND_GOLD
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => fmt(c.raw, M) } } },
      scales: {
        x: { grid: { color: '#f0f0f0' } },
        y: { ticks: { callback: v => fmt(v, M) }, grid: { color: '#f0f0f0' } }
      }
    }
  });
}

function updateMunChartHistUF(uf, M) {
  const ctx = document.getElementById('chart-mun-hist')?.getContext('2d'); if (!ctx) return;
  const series = anos.map((_, ai) =>
    Object.keys(mun_info)
      .filter(id => mun_info[id].uf === uf)
      .reduce((s, id) => s + calcMunVal(id, M, ai), 0)
  );
  if (chMunHist) chMunHist.destroy();
  chMunHist = new Chart(ctx, {
    type: 'line',
    data: {
      labels: anos,
      datasets: [{
        label: ufs_info[uf]?.n || uf,
        data: series,
        borderColor: BRAND_GREEN, backgroundColor: 'rgba(45,90,27,.12)',
        fill: true, tension: .35, pointRadius: 3, pointBackgroundColor: BRAND_GREEN
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => fmt(c.raw, M) } } },
      scales: {
        x: { grid: { color: '#f0f0f0' } },
        y: { ticks: { callback: v => fmt(v, M) }, grid: { color: '#f0f0f0' } }
      }
    }
  });
}

// ═══════════════════════════════════════════════════════════
// CHART — Histórico
// ═══════════════════════════════════════════════════════════
let chHist = null, chTop = null;

function updateHistorico() {
  const ctx = document.getElementById('chart-hist')?.getContext('2d'); if (!ctx) return;
  const M = curMetrica(), uf = state.ufSel, mid = state.microSel;
  let series, label;

  if (mid) {
    series = anos.map((_, ai) => {
      const tmp = state.anoIdx; state.anoIdx = ai;
      const v = calcMic(mid, M); state.anoIdx = tmp; return v;
    });
    label  = mic_info[mid]?.n || mid;
  } else if (uf) {
    series = anos.map((_, ai) => {
      const tmp = state.anoIdx; state.anoIdx = ai;
      const v = calcEst(uf, M); state.anoIdx = tmp; return v;
    });
    label = ufs_info[uf]?.n || uf;
  } else {
    series = anos.map((_, ai) => {
      const tmp = state.anoIdx; state.anoIdx = ai;
      const v = Object.keys(ufs_info).reduce((s, u) => s + calcEst(u, M), 0);
      state.anoIdx = tmp; return v;
    });
    label = 'Brasil';
  }

  if (chHist) chHist.destroy();
  chHist = new Chart(ctx, {
    type: 'line',
    data: {
      labels: anos,
      datasets: [{
        label,
        data: series,
        borderColor: BRAND_GREEN, backgroundColor: 'rgba(45,90,27,.10)',
        fill: true, tension: .35, pointRadius: 3, pointBackgroundColor: BRAND_GREEN
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { tooltip: { callbacks: { label: c => fmt(c.raw, M) } } },
      scales: {
        x: { grid: { color: '#f0f0f0' } },
        y: { ticks: { callback: v => fmt(v, M) }, grid: { color: '#f0f0f0' } }
      }
    }
  });
  document.getElementById('chart-hist-title').textContent =
    '📈 Série Histórica — ' +
    (mid ? (mic_info[mid]?.n || mid) : uf ? (ufs_info[uf]?.n || uf) : 'Brasil') +
    ' — ' + metLabel();

  // Top culturas / categorias
  const ctx2 = document.getElementById('chart-top')?.getContext('2d'); if (!ctx2) return;
  const ai = getAnoIdx();
  const isPec = state.domain === 'pecuaria';
  const cultVals = isPec
    ? getActiveCategoriasPec().map(c => {
        const v = uf
          ? (ppm_est_data?.[uf]?.[c]?.[M]?.[ai] || 0)
          : Object.keys(ufs_info).reduce((s, u) => s + (ppm_est_data?.[u]?.[c]?.[M]?.[ai] || 0), 0);
        return { c, v };
      }).filter(x => x.v > 0).sort((a, b) => b.v - a.v).slice(0, 15)
    : getActiveCulturas().map(c => {
        const v = uf
          ? (est_data[uf]?.[c]?.[M]?.[ai] || 0)
          : Object.keys(ufs_info).reduce((s, u) => s + (est_data[u]?.[c]?.[M]?.[ai] || 0), 0);
        return { c, v };
      }).filter(x => x.v > 0).sort((a, b) => b.v - a.v).slice(0, 15);

  if (chTop) chTop.destroy();
  chTop = new Chart(ctx2, {
    type: 'bar',
    data: {
      labels: cultVals.map(x => x.c),
      datasets: [{ data: cultVals.map(x => x.v), backgroundColor: BRAND_GOLD, borderRadius: 4 }]
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => fmt(c.raw, M) } } },
      scales: {
        x: { ticks: { callback: v => fmt(v, M) }, grid: { color: '#f0f0f0' } },
        y: { ticks: { font: { size: 10 } } }
      }
    }
  });
  document.getElementById('chart-top-title').textContent =
    (isPec ? '🐄 Top Categorias — ' : '🌾 Top Culturas — ') + getAno();
}

// ═══════════════════════════════════════════════════════════
// CHARTS — Rankings
// ═══════════════════════════════════════════════════════════
let chRankUF = null, chRankCult = null, chRankMic = null;

function updateRanking() {
  const M = curMetrica(), ai = getAnoIdx();

  // Top UFs
  const ufVals = Object.keys(ufs_info)
    .map(uf => ({ uf, v: calcEst(uf, M) }))
    .filter(x => x.v > 0).sort((a, b) => b.v - a.v).slice(0, 15);

  const ctx1 = document.getElementById('chart-rank-uf')?.getContext('2d');
  if (ctx1) {
    if (chRankUF) chRankUF.destroy();
    chRankUF = new Chart(ctx1, {
      type: 'bar',
      data: {
        labels: ufVals.map(x => ufs_info[x.uf]?.n || x.uf),
        datasets: [{ data: ufVals.map(x => x.v), backgroundColor: BRAND_GREEN, borderRadius: 4 }]
      },
      options: {
        indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => fmt(c.raw, M) } } },
        scales: {
          x: { ticks: { callback: v => fmt(v, M) }, grid: { color: '#f0f0f0' } },
          y: { ticks: { font: { size: 10 } } }
        }
      }
    });
    document.getElementById('rank-uf-title').textContent = `🏆 Top Estados — ${metLabel()} (${getAno()})`;
  }

  // Top culturas / categorias
  const isPec = state.domain === 'pecuaria';
  const cultVals = isPec
    ? getActiveCategoriasPec().map(c => {
        const v = Object.keys(ufs_info).reduce((s, u) => s + (ppm_est_data?.[u]?.[c]?.[M]?.[ai] || 0), 0);
        return { c, v };
      }).filter(x => x.v > 0).sort((a, b) => b.v - a.v).slice(0, 15)
    : getActiveCulturas().map(c => {
        const v = Object.keys(ufs_info).reduce((s, u) => s + (est_data[u]?.[c]?.[M]?.[ai] || 0), 0);
        return { c, v };
      }).filter(x => x.v > 0).sort((a, b) => b.v - a.v).slice(0, 15);

  const ctx2 = document.getElementById('chart-rank-cult')?.getContext('2d');
  if (ctx2) {
    if (chRankCult) chRankCult.destroy();
    chRankCult = new Chart(ctx2, {
      type: 'bar',
      data: {
        labels: cultVals.map(x => x.c),
        datasets: [{ data: cultVals.map(x => x.v), backgroundColor: BRAND_GOLD, borderRadius: 4 }]
      },
      options: {
        indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => fmt(c.raw, M) } } },
        scales: {
          x: { ticks: { callback: v => fmt(v, M) }, grid: { color: '#f0f0f0' } },
          y: { ticks: { font: { size: 10 } } }
        }
      }
    });
    document.getElementById('rank-cult-title').textContent =
      (isPec ? '🐄 Top Categorias' : '🌱 Top Culturas') + ` — ${metLabel()} (${getAno()})`;
  }

  // Top microrregiões
  const micFilter = state.ufSel;
  const micVals = Object.keys(mic_info)
    .filter(m => !micFilter || mic_info[m].uf === micFilter)
    .map(m => ({ m, v: calcMic(m, M) }))
    .filter(x => x.v > 0).sort((a, b) => b.v - a.v).slice(0, 20);

  const ctx3 = document.getElementById('chart-rank-mic')?.getContext('2d');
  if (ctx3) {
    if (chRankMic) chRankMic.destroy();
    chRankMic = new Chart(ctx3, {
      type: 'bar',
      data: {
        labels: micVals.map(x => mic_info[x.m]?.n || x.m),
        datasets: [{ data: micVals.map(x => x.v), backgroundColor: BRAND_GREEN_MID, borderRadius: 4 }]
      },
      options: {
        indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => fmt(c.raw, M) } } },
        scales: {
          x: { ticks: { callback: v => fmt(v, M) }, grid: { color: '#f0f0f0' } },
          y: { ticks: { font: { size: 10 } } }
        }
      }
    });
    document.getElementById('rank-mic-title').textContent =
      '📍 Top 20 Microrregiões — ' +
      (micFilter ? (ufs_info[micFilter]?.n || micFilter) : 'Brasil') +
      ' (' + getAno() + ')';
  }
}

// ═══════════════════════════════════════════════════════════
// KPIs
// ═══════════════════════════════════════════════════════════
function updateKPIs() {
  if (state.domain === 'pecuaria') { updateKPIsPec(); return; }
  const ai = getAnoIdx(), uf = state.ufSel;
  const ufs  = uf ? [uf] : Object.keys(ufs_info);
  const agg  = { a: 0, p: 0, v: 0 };
  const acts = getActiveCulturas();
  let cultCount = 0;
  ufs.forEach(u => {
    const d = est_data[u]; if (!d) return;
    acts.forEach(c => {
      const dc = d[c]; if (!dc) return;
      const pa = dc.a?.[ai] || 0, pp = dc.p?.[ai] || 0, pv = dc.v?.[ai] || 0;
      if (pa + pp + pv > 0) cultCount++;
      agg.a += pa; agg.p += pp; agg.v += pv;
    });
  });
  const year  = getAno();
  const scope = uf ? (ufs_info[uf]?.n || uf) : 'Brasil';
  document.getElementById('kpi-prod').textContent     = fmt(agg.p, 'p');
  document.getElementById('kpi-prod-sub').textContent = `${scope} · ${year}`;
  document.getElementById('kpi-area').textContent     = fmt(agg.a, 'a');
  document.getElementById('kpi-area-sub').textContent = 'ha colhidos';
  document.getElementById('kpi-val').textContent      = fmt(agg.v, 'v');
  document.getElementById('kpi-val-sub').textContent  = 'mil R$';
  document.getElementById('kpi-cult').textContent     = cultCount.toLocaleString('pt-BR');
  document.getElementById('kpi-cult-sub').textContent = 'culturas com dados';
}

function updateKPIsPec() {
  if (!ppmLoaded) return;
  const ai = getAnoIdx(), uf = state.ufSel, cat = state.categoriaPec;
  const ufs = uf ? [uf] : Object.keys(ufs_info);
  let qtd = 0, val = 0, munCount = 0;
  ufs.forEach(u => {
    const d = ppm_est_data[u]?.[cat]; if (!d) return;
    qtd += d.q?.[ai] || 0; val += d.v?.[ai] || 0;
  });
  Object.keys(mun_info).forEach(mid => {
    if (uf && mun_info[mid].uf !== uf) return;
    const d = ppm_mun_data[mid]?.[cat]; if (!d) return;
    if ((d.q?.[ai] || 0) > 0) munCount++;
  });
  const year  = getAno();
  const scope = uf ? (ufs_info[uf]?.n || uf) : 'Brasil';
  const unit  = PEC_UNITS[cat] || '';
  const isRebanho = state.tipoPec === 'Rebanho';

  document.getElementById('kpi-pec-qtd-title').textContent = isRebanho ? 'Efetivo Total' : 'Quantidade Total';
  document.getElementById('kpi-pec-qtd').textContent     = fmt(qtd, 'q') + (unit ? ' ' + unit : '');
  document.getElementById('kpi-pec-qtd-sub').textContent = `${scope} · ${year}`;
  document.getElementById('kpi-pec-val').textContent     = isRebanho ? '—' : fmt(val, 'v');
  document.getElementById('kpi-pec-val-sub').textContent = isRebanho ? 'não se aplica' : 'mil R$';
  document.getElementById('kpi-pec-cat').textContent     = cat || '—';
  document.getElementById('kpi-pec-cat-sub').textContent = isRebanho ? 'Rebanho' : 'Produção Animal';
  document.getElementById('kpi-pec-mun').textContent     = munCount.toLocaleString('pt-BR');
  document.getElementById('kpi-pec-mun-sub').textContent = `com dados · ${year}`;
}

// ═══════════════════════════════════════════════════════════
// POPULATE SELECTS
// ═══════════════════════════════════════════════════════════
function populateCulturas() {
  const sel = document.getElementById('f-cultura'); if (!sel) return;
  const list = (state.grupoId === 'COL') ? colheitadeiras
    : state.grupoId === 'TRA' ? tratores
    : state.grupoId === 'TEM' ? temporarias
    : state.grupoId === 'PER' ? permanentes
    : culturas;
  sel.innerHTML = '<option value="">Todas do grupo</option>' +
    list.map(c => `<option value="${c}">${c}</option>`).join('');
  sel.value = state.cultura || '';
}

function populateCategoriaPec() {
  const sel = document.getElementById('f-categoria-pec'); if (!sel) return;
  const list = getActiveCategoriasPec() || [];
  sel.innerHTML = list.map(c => `<option value="${c}">${c}</option>`).join('');
  if (!list.includes(state.categoriaPec)) state.categoriaPec = list[0] || '';
  sel.value = state.categoriaPec;
}

function populateMetricaPecOptions() {
  const sel = document.getElementById('f-metrica-pec'); if (!sel) return;
  const isRebanho = state.tipoPec === 'Rebanho';
  sel.innerHTML = isRebanho
    ? '<option value="q" selected>Quantidade (Efetivo)</option>'
    : '<option value="q">Quantidade</option><option value="v">Valor (mil R$)</option>';
  sel.value = state.metricaPec;
}

function populateEstados() {
  const sel = document.getElementById('f-estado'); if (!sel) return;
  const opts = Object.entries(ufs_info).sort((a, b) => a[1].n.localeCompare(b[1].n, 'pt-BR'));
  sel.innerHTML = '<option value="">Todos os estados</option>' +
    opts.map(([uf, i]) => `<option value="${uf}">${i.n} (${uf})</option>`).join('');
  sel.value = state.ufSel || '';
}

function populateMicros() {
  const sel = document.getElementById('f-micro'); if (!sel) return;
  const uf  = state.ufSel;
  const mics = Object.entries(mic_info)
    .filter(([, i]) => !uf || i.uf === uf)
    .sort(([, a], [, b]) => a.n.localeCompare(b.n, 'pt-BR'));
  sel.innerHTML = '<option value="">Todas as microrregiões</option>' +
    mics.map(([id, i]) => `<option value="${id}">${i.n}</option>`).join('');
  sel.value = state.microSel || '';
}

// ═══════════════════════════════════════════════════════════
// ACTIONS
// ═══════════════════════════════════════════════════════════
function selectEstado(uf) {
  state.ufSel = uf; state.microSel = ''; state.munSel = '';
  document.getElementById('f-estado').value = uf;
  populateMicros();
  populateMunicipios();
  showTab('estados');
  refreshAll();
}

function selectMicro(mid) {
  state.microSel = mid;
  document.getElementById('f-micro').value = mid;
  refreshAll();
}

// ═══════════════════════════════════════════════════════════
// DOMAIN (Agrícola / Pecuária) — ppm.json é carregado sob demanda
// na primeira troca para Pecuária, mantendo o load inicial leve.
// ═══════════════════════════════════════════════════════════
function loadPPM() {
  if (ppmLoaded) return Promise.resolve();
  if (ppmLoading) return ppmLoading;
  const btn = document.querySelector('.dom-btn[data-dom="pecuaria"]');
  const original = btn ? btn.textContent : '';
  if (btn) { btn.textContent = '⏳ Carregando…'; btn.disabled = true; }
  ppmLoading = fetch('data/ppm.json')
    .then(r => r.json())
    .then(d => {
      PPM = d;
      ({ rebanho_categorias, producao_categorias,
         est_data: ppm_est_data, mic_data: ppm_mic_data, mun_data: ppm_mun_data } = PPM);
      ppmLoaded = true;
    })
    .catch(e => {
      console.error('Erro ao carregar ppm.json', e);
      alert('Não foi possível carregar os dados de pecuária.');
    })
    .finally(() => {
      if (btn) { btn.textContent = original; btn.disabled = false; }
      ppmLoading = null;
    });
  return ppmLoading;
}

function switchDomain(dom) {
  if (dom === state.domain) return;
  const proceed = () => {
    if (dom === 'pecuaria' && !ppmLoaded) return; // load falhou, permanece no domínio atual
    state.domain = dom;
    document.body.dataset.domain = dom;
    document.querySelectorAll('.dom-btn').forEach(b => b.classList.toggle('active', b.dataset.dom === dom));
    if (dom === 'pecuaria') {
      populateMetricaPecOptions();
      populateCategoriaPec();
    }
    refreshAll();
  };
  if (dom === 'pecuaria' && !ppmLoaded) loadPPM().then(proceed);
  else proceed();
}

// ═══════════════════════════════════════════════════════════
// TABS
// ═══════════════════════════════════════════════════════════
function showTab(name) {
  document.querySelectorAll('.tab-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.tab-pane').forEach(p =>
    p.classList.toggle('active', p.id === 'tab-' + name));
  state.tab = name;
  document.body.dataset.tab = name;
  setTimeout(() => {
    if (mapBR  && (name === 'brasil'  || name === 'ranking')) mapBR.invalidateSize();
    if (mapEst && name === 'estados')  mapEst.invalidateSize();
    if (mapMun && name === 'municipio') mapMun.invalidateSize();
    refreshAll();
  }, 60);
}

// ═══════════════════════════════════════════════════════════
// REFRESH
// ═══════════════════════════════════════════════════════════
function refreshAll() {
  if (state.domain === 'pecuaria' && !ppmLoaded) return;
  updateKPIs();
  const t = state.tab;
  if (t === 'brasil')    updateMapBR();
  if (t === 'estados')   { updateMapBR(); updateMapEst(); updateChartMicro(); }
  if (t === 'municipio') { updateMapMun(); updateMunicipio(); }
  if (t === 'historico') updateHistorico();
  if (t === 'ranking')   { updateMapBR(); updateRanking(); }
  const al = document.getElementById('ano-label');
  if (al) al.textContent = getAno();
}

// ═══════════════════════════════════════════════════════════
// EXPORT
// ═══════════════════════════════════════════════════════════
function exportCSV() {
  const M = curMetrica(), ai = getAnoIdx(), uf = state.ufSel;
  const ufs = uf ? [uf] : Object.keys(ufs_info);
  const isPec = state.domain === 'pecuaria';
  const rows = [['UF', 'Estado', isPec ? 'Categoria' : 'Cultura', metLabel()]];
  ufs.forEach(u => {
    if (isPec) {
      const v = ppm_est_data?.[u]?.[state.categoriaPec]?.[M]?.[ai];
      if (v) rows.push([u, ufs_info[u]?.n || u, state.categoriaPec, v]);
      return;
    }
    const d = est_data[u]; if (!d) return;
    getActiveCulturas().forEach(c => {
      const v = d[c]?.[M]?.[ai]; if (v) rows.push([u, ufs_info[u]?.n || u, c, v]);
    });
  });
  const a = document.createElement('a');
  a.href = 'data:text/csv;charset=utf-8,﻿' +
    encodeURIComponent(rows.map(r => r.join(';')).join('\n'));
  a.download = `${isPec ? 'PPM' : 'PAM'}_${getAno()}_${uf || 'Brasil'}.csv`;
  a.click();
}

function exportJSON() {
  const M = curMetrica(), ai = getAnoIdx(), uf = state.ufSel;
  const isPec = state.domain === 'pecuaria';
  const out = { ano: getAno(), metrica: M, uf: uf || 'BR', data: {} };
  (uf ? [uf] : Object.keys(ufs_info)).forEach(u => {
    if (isPec) {
      const v = ppm_est_data?.[u]?.[state.categoriaPec]?.[M]?.[ai];
      if (v) out.data[u] = { [state.categoriaPec]: v };
      return;
    }
    const d = est_data[u]; if (!d) return; out.data[u] = {};
    getActiveCulturas().forEach(c => {
      const v = d[c]?.[M]?.[ai]; if (v) out.data[u][c] = v;
    });
  });
  const a = document.createElement('a');
  a.href = 'data:application/json,' + encodeURIComponent(JSON.stringify(out));
  a.download = `${isPec ? 'PPM' : 'PAM'}_${getAno()}.json`;
  a.click();
}

// ═══════════════════════════════════════════════════════════
// EVENT BINDINGS
// ═══════════════════════════════════════════════════════════
function bindEvents() {
  document.getElementById('f-metrica').addEventListener('change', e => {
    state.metricaAgro = e.target.value; state.cultura = '';
    populateCulturas(); refreshAll();
  });
  document.getElementById('f-metrica-pec').addEventListener('change', e => {
    state.metricaPec = e.target.value; refreshAll();
  });
  document.getElementById('f-ano').addEventListener('input', e => {
    state.anoIdx = +e.target.value; refreshAll();
  });
  document.querySelectorAll('.grp-btn').forEach(btn => btn.addEventListener('click', () => {
    state.grupoId = btn.dataset.grp; state.cultura = '';
    document.querySelectorAll('.grp-btn').forEach(b => b.classList.toggle('active', b === btn));
    populateCulturas(); refreshAll();
  }));
  document.querySelectorAll('.tipo-pec-btn').forEach(btn => btn.addEventListener('click', () => {
    state.tipoPec = btn.dataset.tipo;
    document.querySelectorAll('.tipo-pec-btn').forEach(b => b.classList.toggle('active', b === btn));
    // "Valor" só existe para Produção — força Quantidade ao entrar em Rebanho
    if (state.tipoPec === 'Rebanho') state.metricaPec = 'q';
    populateMetricaPecOptions();
    populateCategoriaPec();
    refreshAll();
  }));
  document.getElementById('f-cultura').addEventListener('change', e => {
    state.cultura = e.target.value; refreshAll();
  });
  document.getElementById('f-categoria-pec').addEventListener('change', e => {
    state.categoriaPec = e.target.value; refreshAll();
  });
  document.querySelectorAll('.dom-btn').forEach(btn => btn.addEventListener('click', () => {
    switchDomain(btn.dataset.dom);
  }));
  document.getElementById('f-estado').addEventListener('change', e => {
    state.ufSel = e.target.value; state.microSel = ''; state.munSel = '';
    populateMicros(); populateMunicipios(); refreshAll();
  });
  document.getElementById('f-micro').addEventListener('change', e => {
    state.microSel = e.target.value; refreshAll();
  });
  document.getElementById('f-municipio').addEventListener('change', e => {
    state.munSel = e.target.value; updateMunicipio();
  });
  document.querySelectorAll('.tab-btn').forEach(btn => btn.addEventListener('click', () => {
    showTab(btn.dataset.tab);
  }));
}
