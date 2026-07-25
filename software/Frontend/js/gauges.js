// ── Medidores tipo velocímetro (Plotly) ──
// Totalmente autocontenido: nada de aquí lo necesita otro archivo (dashboard-render.js
// actualiza los valores después vía Plotly.update por id, no llamando estas funciones).
(function () {
  function gaugeConfig(value, max, unit, color, steps) {
    return [{
      type: "indicator", mode: "gauge+number", value: value,
      number: { font: { size: 40, color: color, family: "Orbitron" } },
      gauge: {
        axis: { range: [0, max], tickwidth: 1, tickcolor: "#444", tickfont: { color: "#888", size: 10, family: "Share Tech Mono" } },
        bar: { color: color, thickness: 0.28 }, bgcolor: "#0a0a0a", borderwidth: 1, bordercolor: "#222",
        steps: steps
      }
    }];
  }

  var gaugeLayout = { margin: { t: 20, r: 24, l: 24, b: 10 }, paper_bgcolor: "rgba(0,0,0,0)", font: { color: "#888", family: "Share Tech Mono" }, height: 175 };

  Plotly.newPlot('speed_v', gaugeConfig(0, 120, 'km/h', '#3aa8bd', [
    { range: [0, 80], color: '#0a1a1a' }, { range: [80, 100], color: '#1a1a0a' }, { range: [100, 120], color: '#1a0a0a' }
  ]), gaugeLayout, { displayModeBar: false, responsive: true });

  Plotly.newPlot('curr_p', gaugeConfig(0, 120, 'A', '#a85cc0', [
    { range: [0, 70], color: '#0a1a1a' }, { range: [70, 100], color: '#1a1a0a' }, { range: [100, 120], color: '#1a0a0a' }
  ]), gaugeLayout, { displayModeBar: false, responsive: true });

  Plotly.newPlot('rpm', gaugeConfig(0, 5000, 'rpm', '#cc4055', [
    { range: [0, 3000], color: '#0a1a1a' }, { range: [3000, 4000], color: '#1a1a0a' }, { range: [4000, 5000], color: '#1a0a0a' }
  ]), gaugeLayout, { displayModeBar: false, responsive: true });
})();
