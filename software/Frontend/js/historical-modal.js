// ── Modal de sesiones históricas ──
// URLs vienen de FenixConfig (config.js) — antes estaban hardcodeadas aquí
// y duplicadas en websocket.js. Se exponen solo las 5 funciones que el HTML
// llama por onclick (incluido el HTML generado dinámicamente aquí mismo,
// que usa onclick="backToHistPicker()").
(function () {
  var sessionsRequestToken = 0;
  var histRequestToken = 0;

  function openHistModal() {
    var inputFecha = document.getElementById('hist-date');
    if (!inputFecha.value) { inputFecha.value = new Date().toISOString().slice(0, 10); }
    document.getElementById('hist-overlay').classList.add('open');
    fetchSessionsForDate();
  }
  function closeHistModal() {
    document.getElementById('hist-overlay').classList.remove('open');
    document.getElementById('hist-picker-view').style.display = 'block';
    document.getElementById('hist-result-view').style.display = 'none';
    document.getElementById('hist-result-view').innerHTML = '';
  }
  function backToHistPicker() {
    document.getElementById('hist-picker-view').style.display = 'block';
    document.getElementById('hist-result-view').style.display = 'none';
  }

  function fetchSessionsForDate() {
    var fecha = document.getElementById('hist-date').value;
    var selectSesion = document.getElementById('hist-session');
    var msg = document.getElementById('hist-picker-msg');
    if (!fecha) { return; }
    var miToken = ++sessionsRequestToken;
    selectSesion.innerHTML = '<option value="">Cargando…</option>';
    msg.textContent = '';
    fetch(FenixConfig.sessionsForDateUrl + '?date=' + encodeURIComponent(fecha), { cache: 'no-store' })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        if (miToken !== sessionsRequestToken) return; // respuesta vieja — ignorar
        if (res.ok && res.body.sessions && res.body.sessions.length > 0) {
          selectSesion.innerHTML = res.body.sessions.map(function (s) {
            return '<option value="' + escapeHtml(s) + '">Sesión ' + escapeHtml(s) + '</option>';
          }).join('');
        } else {
          selectSesion.innerHTML = '<option value="">— sin sesiones ese día —</option>';
        }
      })
      .catch(function () {
        if (miToken !== sessionsRequestToken) return;
        selectSesion.innerHTML = '<option value="">— error al consultar —</option>';
        msg.textContent = 'No se pudo conectar al backend';
      });
  }

  function renderHistSummary(resumen) {
    var vueltas = resumen.laps || [];
    var nVueltaOptimaHist = (resumen.top_optimas && resumen.top_optimas.length > 0) ? resumen.top_optimas[0].n_lap : null;
    var filasVueltas = vueltas.map(function (vuelta) {
      var esOptima = (nVueltaOptimaHist != null && vuelta.n_lap === nVueltaOptimaHist);
      return buildLapRowHtml({
        n_lap: vuelta.n_lap,
        t_vuelta: vuelta.t_vuelta.toFixed(1),
        delta_mejor: vuelta.delta_mejor,
        d_vuelta: vuelta.d_vuelta.toFixed(3),
        E_vuelta: vuelta.E_vuelta,
        E_regen_vuelta: vuelta.E_regen_vuelta,
        eta_vuelta: vuelta.eta_vuelta,
        vel_max: vuelta.vel_max, vel_prom: vuelta.vel_prom,
        p_hv_max: vuelta.p_hv_max, p_hv_prom: vuelta.p_hv_prom,
        p_regen_max: vuelta.p_regen_max, p_regen_prom: vuelta.p_regen_prom,
        p_mec_max: vuelta.p_mec_max, p_mec_prom: vuelta.p_mec_prom,
        Gx_max: vuelta.Gx_max, Gy_max: vuelta.Gy_max,
        rpm_max: vuelta.rpm_max, rpm_prom: vuelta.rpm_prom
      }, { extraClass: esOptima ? 'optimal' : '', sinEstado: true });
    }).join('');

    var filaTop3 = function (lista, unidad, campo) {
      return lista.map(function (l) {
        var valor = campo === 'score' ? l.score : l[campo];
        return '<div>#' + escapeHtml(l.n_lap) + ' — ' + escapeHtml(valor) + ' ' + unidad + '</div>';
      }).join('') || '<div style="grid-column:span 3">—</div>';
    };

    var html = ''
      + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">'
      + '<span style="font-size:15px;color:var(--green)">Sesión ' + escapeHtml(resumen.session_id) + ' — ' + escapeHtml(resumen.date) + ' · ' + escapeHtml(resumen.n_vueltas) + ' vueltas</span>'
      + '<span style="font-size:13px;color:var(--muted)">Duración: <b style="color:var(--text)">' + fmtDuracionMinSeg(resumen.duracion_s) + '</b></span>'
      + '</div>'

      + '<div class="hist-sec-title">Batería HV / Aux</div>'
      + '<div class="hist-grid" style="grid-template-columns:repeat(3,1fr)">'
      + '<div><span class="hg-lbl">SOC inicial→final</span><span class="hg-val">' + fmtDecimalOGuion(resumen.soc_ini, 0) + '%→' + fmtDecimalOGuion(resumen.soc_fin, 0) + '%</span></div>'
      + '<div><span class="hg-lbl">E.HV/Q.HV inicial→final</span><span class="hg-val">' + fmtDecimalOGuion(resumen.E_HV_ini, 0) + '→' + fmtDecimalOGuion(resumen.E_HV_fin, 0) + 'Wh · ' + fmtDecimalOGuion(resumen.Q_HV_ini, 1) + '→' + fmtDecimalOGuion(resumen.Q_HV_fin, 1) + 'Ah</span></div>'
      + '<div><span class="hg-lbl">SOC aux inicial→final</span><span class="hg-val">' + fmtDecimalOGuion(resumen.soc_aux_ini, 0) + '%→' + fmtDecimalOGuion(resumen.soc_aux_fin, 0) + '%</span></div>'
      + '<div style="grid-column:span 3"><span class="hg-lbl">E.Aux/Q.Aux inicial→final</span><span class="hg-val">' + fmtDecimalOGuion(resumen.E_aux_ini, 1) + '→' + fmtDecimalOGuion(resumen.E_aux_fin, 1) + 'Wh · ' + fmtDecimalOGuion(resumen.Q_aux_ini, 2) + '→' + fmtDecimalOGuion(resumen.Q_aux_fin, 2) + 'Ah</span></div>'
      + '</div>'

      + '<div class="hist-sec-title">Velocidad / RPM / Fuerzas G — promedio</div>'
      + '<div class="hist-grid" style="grid-template-columns:repeat(3,1fr)">'
      + '<div><span class="hg-lbl">Vel promedio/máx</span><span class="hg-val">' + fmtDecimalOGuion(resumen.spd_prom) + '/' + fmtDecimalOGuion(resumen.spd_max) + ' km/h</span></div>'
      + '<div><span class="hg-lbl">RPM promedio/máx</span><span class="hg-val">' + fmtDecimalOGuion(resumen.rpm_prom, 0) + '/' + fmtDecimalOGuion(resumen.rpm_max, 0) + '</span></div>'
      + '<div><span class="hg-lbl">G máx X/Y/Z</span><span class="hg-val">' + fmtDecimalOGuion(resumen.Gx_max, 2) + '/' + fmtDecimalOGuion(resumen.Gy_max, 2) + '/' + fmtDecimalOGuion(resumen.Gz_max, 2) + '</span></div>'
      + '</div>'

      + '<div class="hist-sec-title">Potencia / Corriente / Energía — promedio</div>'
      + '<div class="hist-grid" style="grid-template-columns:repeat(3,1fr)">'
      + '<div><span class="hg-lbl">P.HV promedio/máx</span><span class="hg-val">' + fmtDecimalOGuion(resumen.p_hv_prom, 0) + '/' + fmtDecimalOGuion(resumen.p_hv_max, 0) + ' W</span></div>'
      + '<div><span class="hg-lbl">P.Regen promedio/máx</span><span class="hg-val">' + fmtDecimalOCero(resumen.p_regen_prom, 0) + '/' + fmtDecimalOCero(resumen.p_regen_max, 0) + ' W</span></div>'
      + '<div><span class="hg-lbl">P.Mec promedio/máx</span><span class="hg-val">' + fmtDecimalOGuion(resumen.p_mec_prom, 0) + '/' + fmtDecimalOGuion(resumen.p_mec_max, 0) + ' W</span></div>'
      + '<div><span class="hg-lbl">Corr.batt promedio/máx</span><span class="hg-val">' + fmtDecimalOGuion(resumen.curr_batt_prom) + '/' + fmtDecimalOGuion(resumen.curr_batt_max) + ' A</span></div>'
      + '<div><span class="hg-lbl">Corr.regen promedio/máx</span><span class="hg-val">' + fmtDecimalOCero(resumen.curr_regen_prom) + '/' + fmtDecimalOCero(resumen.curr_regen_max) + ' A</span></div>'
      + '<div><span class="hg-lbl">E cons/regen promedio por vuelta</span><span class="hg-val">' + fmtDecimalOGuion(resumen.E_vuelta_prom, 1) + '/' + fmtDecimalOGuion(resumen.E_regen_vuelta_prom, 1) + ' Wh</span></div>'
      + '</div>'

      + '<div class="hist-sec-title">Temperaturas máximas</div>'
      + '<div class="hist-grid" style="grid-template-columns:repeat(4,1fr)">'
      + '<div><span class="hg-lbl">Motor</span><span class="hg-val">' + fmtDecimalOGuion(resumen.tmp_mot_max, 0) + '°</span></div>'
      + '<div><span class="hg-lbl">Controlador</span><span class="hg-val">' + fmtDecimalOGuion(resumen.tmp_cont_max, 0) + '°</span></div>'
      + '<div><span class="hg-lbl">Capacitores</span><span class="hg-val">' + fmtDecimalOGuion(resumen.tmp_cap_max, 0) + '°</span></div>'
      + '<div><span class="hg-lbl">Batería HV</span><span class="hg-val">' + fmtDecimalOGuion(resumen.tmp_batt_max, 0) + '°</span></div>'
      + '</div>'

      + '<div class="hist-sec-title">Top 3 — tiempo</div>'
      + '<div class="hist-top3">' + filaTop3(resumen.top_tiempo, 's', 't_vuelta') + '</div>'
      + '<div class="hist-sec-title">Top 3 — menor consumo</div>'
      + '<div class="hist-top3">' + filaTop3(resumen.top_consumo, 'Wh', 'E_vuelta') + '</div>'
      + '<div class="hist-sec-title">Top 3 — vueltas más óptimas</div>'
      + '<div class="hist-top3">' + filaTop3(resumen.top_optimas, '', 'score') + '</div>'

      + '<div class="hist-sec-title" style="color:var(--orange)">Tabla de vueltas (idéntica a la vista en vivo)</div>'
      + '<div class="lap-row-head no-estado"><span>Vuelta</span><span>Tiempo</span><span>Δ mejor</span><span>Distancia</span><span>E consumida</span><span>E regenerada</span><span>Eficiencia</span><span>Vel máx/prom</span><span>P.HV máx/prom</span><span>P.Regen máx/prom</span><span>P.Mec máx/prom</span><span>G-X máx</span><span>G-Y máx</span><span>RPM máx/prom</span></div>'
      + '<div>' + (filasVueltas || '<div class="laps-empty-msg">Sin vueltas registradas en esta sesión</div>') + '</div>'

      + '<button class="hist-back" onclick="backToHistPicker()">← Elegir otra sesión</button>';

    document.getElementById('hist-result-view').innerHTML = html;
  }

  function loadHistSession() {
    var fecha = document.getElementById('hist-date').value;
    var sesion = document.getElementById('hist-session').value;
    if (!fecha || !sesion) { alert('Completa fecha y número de sesión'); return; }

    var miToken = ++histRequestToken;
    var vistaResultado = document.getElementById('hist-result-view');
    document.getElementById('hist-picker-view').style.display = 'none';
    vistaResultado.style.display = 'block';
    vistaResultado.innerHTML = '<div class="hist-loading">Consultando InfluxDB…</div>';

    fetch(FenixConfig.sessionSummaryUrl + '?date=' + encodeURIComponent(fecha) + '&session_id=' + encodeURIComponent(sesion), { cache: 'no-store' })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        if (miToken !== histRequestToken) return; // respuesta vieja, ya se pidió otra sesión — ignorar
        if (res.ok) { renderHistSummary(res.body); }
        else { vistaResultado.innerHTML = '<div class="hist-err">Error: ' + escapeHtml(res.body.error || 'desconocido') + '</div><button class="hist-back" onclick="backToHistPicker()">← Elegir otra sesión</button>'; }
      })
      .catch(function () {
        if (miToken !== histRequestToken) return;
        vistaResultado.innerHTML = '<div class="hist-err">No se pudo conectar al backend</div><button class="hist-back" onclick="backToHistPicker()">← Elegir otra sesión</button>';
      });
  }

  window.openHistModal = openHistModal;
  window.closeHistModal = closeHistModal;
  window.fetchSessionsForDate = fetchSessionsForDate;
  window.loadHistSession = loadHistSession;
  window.backToHistPicker = backToHistPicker;
})();
