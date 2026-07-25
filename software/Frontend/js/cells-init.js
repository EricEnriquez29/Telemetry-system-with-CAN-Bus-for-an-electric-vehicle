// ── Generación de las 16 celdas de voltaje + 16 de resistencia interna ──
// Totalmente autocontenido: solo crea nodos DOM una vez al cargar, nadie
// más necesita nada de este archivo.
(function () {
  var contenedorVoltajes = document.getElementById('celdas-voltaje');
  for (var i = 1; i <= 16; i++) {
    var celda = document.createElement('div');
    celda.className = 'cell-item';
    celda.innerHTML = '<div class="ci-n">C' + i + '</div><div class="ci-v" id="cell_volts_' + i + '">—</div>';
    contenedorVoltajes.appendChild(celda);
  }

  var contenedorResistencias = document.getElementById('celdas-resistencia');
  for (var j = 1; j <= 16; j++) {
    var celdaR = document.createElement('div');
    celdaR.className = 'cell-item';
    celdaR.innerHTML = '<div class="ci-n">C' + j + '</div><div class="ci-v" id="celda-res-' + j + '">—</div>';
    contenedorResistencias.appendChild(celdaR);
  }
})();
