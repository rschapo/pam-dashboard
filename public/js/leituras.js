/* Leituras do território: as regras de cálculo e de classe das métricas novas do
   painel (densidade, vocação, densidades prontas, cultura dominante e produtores).
   Funções puras, sem DOM nem estado: o mesmo arquivo roda no navegador
   (window.LEITURAS, usado pelo main.js) e nos testes em node
   (generator/complementary/tests/test_leituras_js.py). */
'use strict';

const LEITURAS = (() => {

const HA_POR_KM2 = 100;

// Densidade de um recorte: soma das áreas ÷ soma dos territórios, em ha/km². Nunca a
// média das densidades dos municípios, que faria um município de 10 km² pesar como um
// de 10 mil. `areas` e `territoriosHa` são listas; ausente (null) não soma.
function densidade(areas, territoriosHa) {
  let a = 0, t = 0, algum = false;
  for (const x of areas) if (x != null && isFinite(x)) { a += x; algum = true; }
  for (const x of territoriosHa) if (x != null && x > 0) t += x;
  return algum && t > 0 ? a / (t / HA_POR_KM2) : null;
}

// Vocação: quanto da área colhida do PRÓPRIO território é da seleção, em %. Separa
// "município canavieiro" de "município grande que tem cana".
function vocacao(areaSelecao, areaTotal) {
  return areaTotal > 0 && areaSelecao != null && isFinite(areaSelecao)
    ? areaSelecao / areaTotal * 100 : null;
}

// Razão de duas somas (cadastros por mil ha, por km²). Sem denominador não há medida.
function razaoSomas(num, den, fator = 1) {
  return den > 0 && num != null ? num / den * fator : null;
}

// Cortes de classe por quantis calculados SÓ sobre os valores positivos. Com cultura
// concentrada, a maioria dos territórios tem zero: quantis sobre todos colapsam em "0"
// e o mapa fica de uma cor. O zero cai na primeira classe ("0 a < x"); ausente não
// entra (fica cinza). Cortes repetidos viram uma classe só.
function classesQuantis(vals, nClasses) {
  const pos = vals.filter(x => x != null && isFinite(x) && x > 0).sort((a, b) => a - b);
  if (!pos.length) return [];
  const cortes = [];
  for (let i = 1; i < nClasses; i++) cortes.push(pos[Math.floor(i * pos.length / nClasses)]);
  return [...new Set(cortes)];
}

// Índice da classe do valor; -1 para ausente.
function classe(v, cortes) {
  if (v == null || !isFinite(v)) return -1;
  let i = 0;
  while (i < cortes.length && v >= cortes[i]) i++;
  return i;
}

// Casas decimais pela ordem de grandeza do MENOR corte, com dois algarismos
// significativos: 0,03 ha/km² não pode virar "0,0", e 1.250 não precisa de vírgula.
// Se dois cortes vizinhos saírem iguais na tela, ganha mais uma casa (até 4).
function casas(cortes) {
  const pos = cortes.filter(x => x > 0);
  if (!pos.length) return 0;
  let d = Math.max(0, 1 - Math.floor(Math.log10(Math.min(...pos))));
  const arred = (x, k) => Math.round(x * 10 ** k) / 10 ** k;
  while (d < 4 && pos.some((x, i) => i && arred(x, d) === arred(pos[i - 1], d))) d++;
  return Math.min(d, 4);
}

// Texto de cada corte com dois algarismos significativos, cada um na sua ordem de
// grandeza (0,0024 · 0,038 · 1,2 · 250); vizinhos que sairiam iguais ganham casas.
function textosCortes(cortes) {
  const sig = x => x > 0 ? Math.max(0, 1 - Math.floor(Math.log10(x))) : 0;
  const d = cortes.map(sig);
  const arred = (x, k) => Math.round(x * 10 ** k) / 10 ** k;
  for (let volta = 0; volta < 6; volta++) {
    let mudou = false;
    for (let i = 1; i < cortes.length; i++) {
      const k = Math.max(d[i], d[i - 1]);
      if (k < 6 && arred(cortes[i], k) === arred(cortes[i - 1], k)) { d[i] = d[i - 1] = k + 1; mudou = true; }
    }
    if (!mudou) break;
  }
  return new Map(cortes.map((x, i) => [x, x.toLocaleString('pt-BR', { maximumFractionDigits: d[i] })]));
}

// Rótulos da legenda de classes: "0 a < x", "x a < y", …, "≥ z".
function rotulosClasses(cortes, fmt) {
  if (!cortes.length) return [];
  const r = [`0 a < ${fmt(cortes[0])}`];
  for (let i = 1; i < cortes.length; i++) r.push(`${fmt(cortes[i - 1])} a < ${fmt(cortes[i])}`);
  r.push(`≥ ${fmt(cortes[cortes.length - 1])}`);
  return r;
}

// Cor de cada classe espalhada pela rampa inteira: com 3 classes, as pontas e o meio.
function corDaClasse(i, nClasses, paleta) {
  if (i < 0) return null;
  if (nClasses <= 1) return paleta[paleta.length - 1];
  return paleta[Math.round(i * (paleta.length - 1) / (nClasses - 1))];
}

// Categoria de maior área; empate desfeito pela ordem das categorias (a mesma do export).
function dominante(areas, ordem) {
  let melhor = null, maior = 0;
  for (const k of ordem) {
    const v = areas[k];
    if (v > maior) { maior = v; melhor = k; }
  }
  return melhor;
}

// Soma as áreas por categoria de um conjunto de municípios.
function somaCategorias(registros) {
  const s = {};
  for (const r of registros) for (const [k, v] of Object.entries((r && r.c) || {})) s[k] = (s[k] || 0) + v;
  return s;
}

return { HA_POR_KM2, densidade, vocacao, razaoSomas, classesQuantis, classe, casas,
         textosCortes, rotulosClasses, corDaClasse, dominante, somaCategorias };
})();

if (typeof module === 'object' && module.exports) module.exports = LEITURAS;
