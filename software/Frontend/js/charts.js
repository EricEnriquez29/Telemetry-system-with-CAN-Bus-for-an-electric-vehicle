// ── Gráficas de líneas en tiempo real (Chart.js) ──
// dashboard-render.js necesita empujar datos a estas 4 gráficas en cada
// mensaje, así que se exponen agrupadas en FenixCharts en vez de dejar
// cA/cTM/cPWR/cRegen sueltas en el global.
(function () {
  var VENTANA_MS = 15000;

  function crearGrafica(id, datasets, scales) {
    return new Chart(document.getElementById(id).getContext('2d'), {
      type: 'line', data: { datasets },
      options: {
        animation: false, responsive: true, maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: true, position: 'top', labels: { boxWidth: 8, font: { size: 9, family: 'Share Tech Mono' }, color: '#ccc' } },
          tooltip: {
            backgroundColor: '#0d0d0d', borderColor: '#333', borderWidth: 1,
            titleColor: '#ccc', bodyColor: '#f0f0f0',
            titleFont: { family: 'Share Tech Mono', size: 10 }, bodyFont: { family: 'Share Tech Mono', size: 10 },
            padding: 8,
            callbacks: { title: function (items) { return items.length ? fmtHMS(items[0].parsed.x) : ''; } }
          }
        },
        scales
      }
    });
  }

  function fmtHMS(ms) {
    var d = new Date(ms);
    return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0') + ':' + String(d.getSeconds()).padStart(2, '0');
  }

  var ejeTiempo = { type: 'linear', ticks: { color: '#888', maxTicksLimit: 6, font: { size: 8 }, callback: function (v) { return fmtHMS(v); } }, grid: { color: '#0d0d0d' } };

  var graficaVelocidad = crearGrafica('chart-velocidad-rpm', [
    { label: 'Vel km/h', data: [], borderColor: '#3aa8bd', borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0, yAxisID: 'yL' },
    { label: 'RPM', data: [], borderColor: '#cc4055', borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0, yAxisID: 'yRPM' },
    { label: 'Throttle%', data: [], borderColor: '#d9621a', backgroundColor: 'rgba(217,98,26,0.08)', borderWidth: 2, pointRadius: 0, fill: true, tension: 0, yAxisID: 'yR' },
  ], { x: ejeTiempo, yL: { position: 'left', min: 0, max: 130, ticks: { color: '#3aa8bd', font: { size: 8, family: 'Share Tech Mono' } }, grid: { color: '#0d0d0d' } }, yRPM: { position: 'left', min: 0, max: 7000, ticks: { color: '#cc4055', font: { size: 8, family: 'Share Tech Mono' } }, grid: { drawOnChartArea: false } }, yR: { position: 'right', min: 0, max: 100, ticks: { color: '#d9621a', font: { size: 8, family: 'Share Tech Mono' } }, grid: { drawOnChartArea: false } } });

  var graficaTorquePotencia = crearGrafica('chart-torque-potencia', [
    { label: 'Torque Nm', data: [], borderColor: '#d9621a', borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0, yAxisID: 'yNm' },
    { label: 'P.Mec W', data: [], borderColor: '#3ba776', borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0, yAxisID: 'yW' },
    { label: 'P.HV W', data: [], borderColor: '#a85cc0', backgroundColor: 'rgba(168,92,192,0.06)', borderWidth: 2, pointRadius: 0, fill: true, tension: 0, yAxisID: 'yPHV', spanGaps: false },
  ], { x: ejeTiempo, yNm: { position: 'right', min: 0, max: 35, ticks: { color: '#d9621a', font: { size: 8, family: 'Share Tech Mono' } }, grid: { drawOnChartArea: false } }, yW: { position: 'left', min: 0, suggestedMax: 6000, ticks: { color: '#3ba776', font: { size: 8, family: 'Share Tech Mono' } }, grid: { color: '#0d0d0d' } }, yPHV: { position: 'left', min: 0, suggestedMax: 10000, ticks: { color: '#a85cc0', font: { size: 8, family: 'Share Tech Mono' } }, grid: { drawOnChartArea: false } } });

  var graficaPotenciaCorriente = crearGrafica('chart-potencia-corriente', [
    { label: 'P.HV W', data: [], borderColor: '#a85cc0', borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0, yAxisID: 'yW2', spanGaps: false },
    { label: 'Corriente descarga A', data: [], borderColor: '#3aa8bd', borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0, yAxisID: 'yA2', spanGaps: false },
    { label: 'Throttle%', data: [], borderColor: '#d9621a', backgroundColor: 'rgba(217,98,26,0.08)', borderWidth: 2, pointRadius: 0, fill: true, tension: 0, yAxisID: 'yT2' },
  ], { x: ejeTiempo, yW2: { position: 'left', min: 0, suggestedMax: 10000, ticks: { color: '#a85cc0', font: { size: 8, family: 'Share Tech Mono' } }, grid: { color: '#0d0d0d' } }, yA2: { position: 'left', min: 0, max: 250, ticks: { color: '#3aa8bd', font: { size: 8, family: 'Share Tech Mono' } }, grid: { drawOnChartArea: false } }, yT2: { position: 'right', min: 0, max: 100, ticks: { color: '#d9621a', font: { size: 8, family: 'Share Tech Mono' } }, grid: { drawOnChartArea: false } } });

  var graficaRegen = crearGrafica('chart-regen', [
    { label: 'P.Regen W', data: [], borderColor: '#3ba776', borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0, yAxisID: 'yWR', spanGaps: false },
    { label: 'Freno%', data: [], borderColor: '#cc4055', backgroundColor: 'rgba(204,64,85,0.08)', borderWidth: 2, pointRadius: 0, fill: true, tension: 0, yAxisID: 'yBR' },
    { label: 'Corriente regen A', data: [], borderColor: '#3aa8bd', borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0, yAxisID: 'yAR', spanGaps: false },
  ], { x: ejeTiempo, yWR: { position: 'left', min: 0, suggestedMax: 3000, ticks: { color: '#3ba776', font: { size: 8, family: 'Share Tech Mono' } }, grid: { color: '#0d0d0d' } }, yBR: { position: 'right', min: 0, max: 100, ticks: { color: '#cc4055', font: { size: 8, family: 'Share Tech Mono' } }, grid: { drawOnChartArea: false } }, yAR: { position: 'left', min: 0, max: 250, ticks: { color: '#3aa8bd', font: { size: 8, family: 'Share Tech Mono' } }, grid: { drawOnChartArea: false } } });

  function pushPunto(grafica, indiceDataset, timestamp, valor) {
    var ahora = new Date(timestamp).getTime() || Date.now();
    grafica.data.datasets[indiceDataset].data.push({ x: ahora, y: valor });
    while (grafica.data.datasets[indiceDataset].data.length > 0 && grafica.data.datasets[indiceDataset].data[0].x < ahora - VENTANA_MS) {
      grafica.data.datasets[indiceDataset].data.shift();
    }
    grafica.options.scales.x.min = ahora - VENTANA_MS;
    grafica.options.scales.x.max = ahora;
  }

  window.FenixCharts = {
    push: pushPunto,
    velocidad: graficaVelocidad,
    torquePotencia: graficaTorquePotencia,
    potenciaCorriente: graficaPotenciaCorriente,
    regen: graficaRegen
  };
})();
