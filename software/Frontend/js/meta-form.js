// ── Formulario de línea de meta ──
// El token de acceso YA NO se valida aquí (antes había un META_PASS visible
// en el código fuente del navegador). Ahora solo se envía al backend, que es
// quien decide si es correcto (ver software/Backend/fenix_backend.py, clase
// _MetaHandler). Esto no cifra el token en tránsito (sigue siendo HTTP) —
// eso requiere que el backend tenga TLS — pero cierra el hueco de que
// cualquiera pudiera leer la contraseña abriendo el inspector del navegador.
(function () {
  function setMetaLine() {
    var msg = document.getElementById('meta-msg');
    var token = document.getElementById('meta-pass').value;
    var latA = parseFloat(document.getElementById('meta-lat-a').value);
    var lonA = parseFloat(document.getElementById('meta-lon-a').value);
    var latB = parseFloat(document.getElementById('meta-lat-b').value);
    var lonB = parseFloat(document.getElementById('meta-lon-b').value);

    if (!token) { msg.textContent = 'Ingresa el código de acceso'; msg.className = 'meta-msg err'; return; }
    if ([latA, lonA, latB, lonB].some(isNaN)) { msg.textContent = 'Completa las 4 coordenadas'; msg.className = 'meta-msg err'; return; }

    msg.textContent = 'Enviando…'; msg.className = 'meta-msg';
    fetch(FenixConfig.setMetaUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Meta-Token': token },
      body: JSON.stringify({ lat_a: latA, lon_a: lonA, lat_b: latB, lon_b: lonB })
    })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, status: r.status, body: j }; }); })
      .then(function (res) {
        if (res.ok) {
          msg.textContent = 'Línea de meta seteada ✓'; msg.className = 'meta-msg ok';
          document.getElementById('meta-pass').value = '';
          drawMetaLine(latA, lonA, latB, lonB);
        } else if (res.status === 401) {
          msg.textContent = 'Código de acceso incorrecto'; msg.className = 'meta-msg err';
        } else {
          msg.textContent = 'Error: ' + (res.body.error || 'desconocido'); msg.className = 'meta-msg err';
        }
      })
      .catch(function () { msg.textContent = 'No se pudo conectar al backend'; msg.className = 'meta-msg err'; });
  }

  window.setMetaLine = setMetaLine;
})();
