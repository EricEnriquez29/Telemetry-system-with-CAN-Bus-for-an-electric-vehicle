// ── test_automatizado.js — Pruebas automatizadas del Frontend ──
// Cubre las funciones puras de utils.js (formato de números, escape HTML,
// construcción de fila de tabla de vueltas). No prueba nada que dependa
// del DOM real, WebSocket, Canvas o WebGL (dashboard-render.js,
// canvas-widgets.js, horizon3d.js, etc.) — esas partes se siguen
// verificando a mano en el navegador.
//
// Usa el test runner integrado de Node (node:test) — no agrega ninguna
// dependencia nueva al proyecto (no hay npm install que hacer).
//
// Cómo correrlas:
//   cd software/Frontend
//   node --test js/test_automatizado.js
//
// Ver la sección "Pruebas automatizadas" en README.md para más contexto.

const test = require('node:test');
const assert = require('node:assert/strict');
const {
  num, fmtMaxProm, fmtDuracionMinSeg, fmtDecimalOGuion, fmtDecimalOCero,
  escapeHtml, buildLapRowHtml
} = require('./utils.js');

test('num() — valores no numéricos dan 0', () => {
  assert.equal(num(null), 0);
  assert.equal(num(undefined), 0);
  assert.equal(num('abc'), 0);
});

test('num() — string numérico se convierte a número', () => {
  assert.equal(num('5.2'), 5.2);
  assert.equal(num(0), 0);
});

test('fmtDuracionMinSeg() — formatea segundos como min:seg', () => {
  assert.equal(fmtDuracionMinSeg(125), '2:05');
  assert.equal(fmtDuracionMinSeg(0), '0:00');
  assert.equal(fmtDuracionMinSeg(59), '0:59');
});

test('fmtMaxProm() — ambos null da guiones', () => {
  assert.equal(fmtMaxProm(null, null), '—/—');
});

test('fmtMaxProm() — valores reales con decimales', () => {
  assert.equal(fmtMaxProm(120.456, 80.123, 1), '120.5/80.1');
});

test('fmtMaxProm() — ceroSiNulo devuelve 0 en vez de guion', () => {
  assert.equal(fmtMaxProm(null, null, 0, true), '0/0');
});

test('fmtDecimalOGuion() — null da guion, valor da decimal', () => {
  assert.equal(fmtDecimalOGuion(null), '—');
  assert.equal(fmtDecimalOGuion(3.14159, 2), '3.14');
});

test('escapeHtml() — neutraliza etiquetas y comillas', () => {
  const resultado = escapeHtml('<script>alert(1)</script>');
  assert.ok(!resultado.includes('<script>'));
  assert.equal(escapeHtml('5 < 10 & "ok"'), '5 &lt; 10 &amp; &quot;ok&quot;');
});

test('buildLapRowHtml() — genera 15 celdas cuando incluye estado', () => {
  const html = buildLapRowHtml({
    n_lap: 1, t_vuelta: '80.1', delta_mejor: 0, d_vuelta: '1.234',
    E_vuelta: 120, E_regen_vuelta: 5, eta_vuelta: 97.2,
    vel_max: 60, vel_prom: 40, p_hv_max: 2000, p_hv_prom: 1200,
    p_regen_max: 200, p_regen_prom: 50, p_mec_max: 1800, p_mec_prom: 1000,
    Gx_max: 0.5, Gy_max: 0.4, rpm_max: 4000, rpm_prom: 2500, estado: 'Completa'
  });
  const celdas = (html.match(/lap-cell/g) || []).length;
  assert.equal(celdas, 15);
  assert.ok(html.includes('Completa'));
});

test('buildLapRowHtml() — sinEstado omite la columna de estado', () => {
  const html = buildLapRowHtml({
    n_lap: 1, t_vuelta: '80.1', delta_mejor: null, d_vuelta: '1.234',
    E_vuelta: null, E_regen_vuelta: null, eta_vuelta: null,
  }, { sinEstado: true });
  assert.ok(!html.includes('Completa'));
  assert.ok(html.includes('no-estado'));
});

test('buildLapRowHtml() — escapa valores para evitar XSS', () => {
  const html = buildLapRowHtml({
    n_lap: '<img src=x onerror=alert(1)>', t_vuelta: '1', delta_mejor: null,
    d_vuelta: '1', E_vuelta: null, E_regen_vuelta: null, eta_vuelta: null,
  });
  assert.ok(!html.includes('<img'));
});
