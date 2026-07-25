// ── Orquestador principal ──
// Recibe cada mensaje del WebSocket (websocket.js llama a updateDashboard)
// y actualiza todos los widgets. Solo updateDashboard se expone; el resto
// de las funciones auxiliares (renderLapsTable, updateLapSummary...) y el
// estado de sesión quedan privados dentro del IIFE.
(function () {
  function renderLapsTable(laps, armado, nLap, tActual, dActual, eActual, eRegenActual, nOpt, d) {
    var wrap = document.getElementById('filas-vueltas');
    if (!armado && (!laps || laps.length === 0)) {
      wrap.innerHTML = '<div class="laps-empty-msg" id="laps-empty-msg">Esperando primer cruce de meta…</div>';
      return;
    }

    var filasHtml = (laps || []).map(function (vuelta) {
      var esOptima = (nOpt != null && vuelta.n_lap === nOpt);
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
        rpm_max: vuelta.rpm_max, rpm_prom: vuelta.rpm_prom,
        estado: 'Completa'
      }, { extraClass: esOptima ? 'optimal' : '' });
    }).join('');

    if (armado) {
      filasHtml += buildLapRowHtml({
        n_lap: nLap + 1,
        t_vuelta: tActual.toFixed(1),
        delta_mejor: null,
        d_vuelta: dActual.toFixed(3),
        E_vuelta: eActual,
        E_regen_vuelta: eRegenActual,
        eta_vuelta: null,
        vel_max: d.vel_max_actual, vel_prom: d.vel_prom_actual,
        p_hv_max: d.p_hv_max_actual, p_hv_prom: d.p_hv_prom_actual,
        p_regen_max: d.p_regen_max_actual, p_regen_prom: d.p_regen_prom_actual,
        p_mec_max: d.p_mec_max_actual, p_mec_prom: d.p_mec_prom_actual,
        Gx_max: d.Gx_max_actual, Gy_max: d.Gy_max_actual,
        rpm_max: d.rpm_max_actual, rpm_prom: d.rpm_prom_actual,
        estado: 'En curso…'
      }, { extraClass: 'current' });
    }

    wrap.innerHTML = filasHtml;
  }

  var lastSessionId = null;
  var sessionStartTime = null;
  function updateSessionClock() {
    var el = document.getElementById('duracion-sesion');
    if (!el || sessionStartTime == null) { if (el) el.textContent = '00:00'; return; }
    var segundosTranscurridos = Math.floor((Date.now() - sessionStartTime) / 1000);
    el.textContent = fmtDuracionMinSeg(segundosTranscurridos);
  }
  setInterval(updateSessionClock, 1000);

  function renderEstimates(dRest, nRest, tRest) {
    document.getElementById('estimado-distancia-restante').innerHTML = (dRest != null ? dRest.toFixed(2) : '—') + '<span style="font-size:11px;color:var(--muted)"> km</span>';
    document.getElementById('estimado-vueltas-restantes').textContent = (nRest != null) ? nRest.toFixed(1) : '—';
    document.getElementById('estimado-tiempo-restante').innerHTML = (tRest != null ? tRest.toFixed(0) : '—') + '<span style="font-size:11px;color:var(--muted)"> s</span>';
  }

  function updateLapSummary(armado, nLap, tActual, laps, nRest, tRest, nOpt) {
    var vueltaActual = armado ? (nLap + 1) : '—';
    document.getElementById('resumen-vuelta-actual').textContent = vueltaActual;
    document.getElementById('resumen-tiempo-vuelta').textContent = armado ? tActual.toFixed(1) + 's' : '—';

    var anterior = (laps && laps.length > 0) ? laps[laps.length - 1] : null;
    document.getElementById('resumen-tiempo-anterior').textContent = anterior ? anterior.t_vuelta.toFixed(1) + 's' : '—';

    document.getElementById('resumen-vueltas-restantes').textContent = (nRest != null) ? nRest.toFixed(1) : '—';
    document.getElementById('resumen-tiempo-restante').textContent = (tRest != null) ? tRest.toFixed(0) + 's' : '—';

    if (laps && laps.length > 0) {
      var mejorTiempo = Math.min.apply(null, laps.map(function (l) { return l.t_vuelta; }));
      document.getElementById('resumen-mejor-tiempo').textContent = mejorTiempo.toFixed(1) + 's';

      var vueltasConEnergia = laps.filter(function (l) { return l.E_vuelta != null; });
      if (vueltasConEnergia.length > 0) {
        var mejorEnergia = Math.min.apply(null, vueltasConEnergia.map(function (l) { return l.E_vuelta; }));
        document.getElementById('resumen-mejor-consumo').textContent = mejorEnergia.toFixed(1) + ' Wh';
      } else {
        document.getElementById('resumen-mejor-consumo').textContent = '—';
      }
    } else {
      document.getElementById('resumen-mejor-tiempo').textContent = '—';
      document.getElementById('resumen-mejor-consumo').textContent = '—';
    }

    document.getElementById('resumen-mejor-vuelta').textContent = (nOpt != null) ? ('#' + nOpt) : '—';
  }

  // Envuelto completo en try/catch para que un campo faltante/malformado en
  // un mensaje no deje partes del dashboard congeladas en silencio (antes
  // solo la tabla de vueltas tenía este guard).
  function updateDashboard(payload) {
    try {
      const d = payload.data || {};
      const ts = payload.timestamp || new Date().toISOString();
      const tms = new Date(ts.replace(" ", "T")).getTime() || Date.now();

      var speed_v = num(d.speed_v), rpm = Math.abs(num(d.rpm)), throttle = num(d.throttle), brake = num(d.brake);
      var curr_p = num(d.curr_p), volt_p = num(d.volt_p), soc = num(d.soc);
      var curr_rms = num(d.curr_rms), batt_curr = num(d.batt_curr), ksy_v = num(d.ksy_v);
      var tmp_mot = num(d.tmp_mot), tmp_cont = num(d.tmp_cont), tmp_cap = num(d.tmp_cap), tmp_max = num(d.tmp_max);
      var volt_a = num(d.volt_a), curr_a = num(d.curr_a);
      var odo_veh = num(d.odo_veh), cont_st = Math.round(num(d.cont_st));
      var torq = num(d.tau_est);

      drawMetaLine(d.meta_lat_a, d.meta_lon_a, d.meta_lat_b, d.meta_lon_b);

      renderLapsTable(d.laps, !!d.armado, Math.round(num(d.n_lap)), num(d.t_vuelta), num(d.d_vuelta), d.E_vuelta_actual, d.E_regen_vuelta_actual, d.n_opt, d);
      renderEstimates(d.d_rest, d.n_rest, d.t_rest);
      updateLapSummary(!!d.armado, Math.round(num(d.n_lap)), num(d.t_vuelta), d.laps, d.n_rest, d.t_rest, d.n_opt);

      document.getElementById('ultimo-dato-ts').textContent = ts;
      document.getElementById('veh-id').textContent = payload.vehicle_id != null ? payload.vehicle_id : '—';
      document.getElementById('sesion-id').textContent = payload.session_id != null ? payload.session_id : '—';
      if (payload.session_id != null && payload.session_id !== lastSessionId) {
        lastSessionId = payload.session_id;
        sessionStartTime = Date.now();
      }
      setMgtConn(d.mgt_conectado);

      updateRev(rpm / 5000);
      Plotly.update('speed_v', { value: [speed_v] }, {}, [0]);
      Plotly.update('rpm', { value: [rpm] }, {}, [0]);
      Plotly.update('curr_p', { value: [curr_p < 0 ? Math.abs(curr_p) : 0] }, {}, [0]);

      drawBattery(Math.round(soc));
      drawOdo(odo_veh);
      drawContactor(cont_st === 1);
      document.getElementById('cont_st').textContent = cont_st === 1 ? 'CONTACTOR CERRADO' : 'CONTACTOR ABIERTO';

      setThermo('tmp_mot', tmp_mot, 150); setThermo('tmp_cont', tmp_cont, 100);
      setThermo('tmp_cap', tmp_cap, 100); setThermo('tmp_max', tmp_max, 60);

      document.getElementById('throttle-barra').style.width = throttle + '%';
      document.getElementById('brake-barra').style.width = brake + '%';
      document.getElementById('throttle-valor').textContent = throttle.toFixed(0) + '%';
      document.getElementById('brake-valor').textContent = brake.toFixed(0) + '%';

      var p_mec = num(d.p_mec), p_hv = d.p_hv;
      var v_rest = d.v_rest_pack;
      var eta = d.eta;
      var etabat = d.eta_bat;

      document.getElementById('motor-eficiencia').innerHTML = (eta != null ? eta.toFixed(1) : '—') + '<span class="rl-unit">%</span>';
      document.getElementById('curr_rms').innerHTML = curr_rms.toFixed(1) + '<span class="rl-unit">A</span>';
      document.getElementById('ksy_v').innerHTML = ksy_v.toFixed(1) + '<span class="rl-unit">V</span>';
      document.getElementById('batt_curr').innerHTML = batt_curr.toFixed(1) + '<span class="rl-unit">A</span>';
      document.getElementById('energia-consumida').innerHTML = num(d.E_HV).toFixed(1) + '<span class="rl-unit">Wh</span>';
      document.getElementById('carga-consumida').innerHTML = num(d.Q_HV).toFixed(2) + '<span class="rl-unit">Ah</span>';
      document.getElementById('energia-regenerada').innerHTML = num(d.E_regen).toFixed(1) + '<span class="rl-unit">Wh</span>';
      document.getElementById('energia-restante').innerHTML = num(d.E_HV_rest).toFixed(1) + '<span class="rl-unit">Wh</span>';
      document.getElementById('carga-restante').innerHTML = num(d.Q_HV_rest).toFixed(2) + '<span class="rl-unit">Ah</span>';

      document.getElementById('volt_a').innerHTML = volt_a.toFixed(1) + '<span class="rl-unit">V</span>';
      document.getElementById('curr_a').innerHTML = curr_a.toFixed(1) + '<span class="rl-unit">A</span>';
      document.getElementById('aux-soc').innerHTML = (d.soc_aux != null ? num(d.soc_aux).toFixed(1) : '—') + '<span class="rl-unit">%</span>';
      document.getElementById('aux-potencia').innerHTML = num(d.p_aux).toFixed(1) + '<span class="rl-unit">W</span>';

      var Gx = num(d.Gx), Gy = num(d.Gy), Gz = num(d.Gz);
      drawGMeter(Gx, Gy);
      document.getElementById('gmeter-gz-valor').textContent = Gz.toFixed(2);

      updateHorizon(num(d.phi), num(d.theta));

      document.getElementById('volt_p').innerHTML = volt_p.toFixed(1) + '<span class="rl-unit">V</span>';
      document.getElementById('bateria-eficiencia').innerHTML = (etabat != null ? etabat.toFixed(1) : '—') + '<span class="rl-unit">%</span>';

      drawSag(volt_p, curr_p);

      document.getElementById('soh-porcentaje').innerHTML = (d.soh_c != null ? num(d.soh_c).toFixed(1) : '—') + '<span class="rl-unit">%</span>';
      document.getElementById('pack-resistencia').innerHTML = (d.r_pack != null ? (num(d.r_pack) * 1000).toFixed(1) : '—') + '<span class="rl-unit">mΩ</span>';
      document.getElementById('voltaje-reposo').innerHTML = (v_rest != null ? num(v_rest).toFixed(1) : '—') + '<span class="rl-unit">V</span>';
      var sohActivo = d.soh_activo === true;
      var elSohActivo = document.getElementById('soh-estado');
      elSohActivo.textContent = sohActivo ? 'activo' : 'inactivo';
      elSohActivo.className = sohActivo ? 'diag-on' : 'diag-off';
      document.getElementById('soh-soc-inicio').textContent = (d.soh_soc_inicio != null ? num(d.soh_soc_inicio).toFixed(1) + ' %' : '—');
      document.getElementById('soh-carga-acumulada').textContent = (d.soh_Q_SOH != null ? num(d.soh_Q_SOH).toFixed(3) + ' Ah' : '—');
      document.getElementById('tiempo-reposo').textContent = num(d.t_reposo_s).toFixed(0) + ' s';

      var resistenciaCeldas = d.r_cells || {};
      for (var i = 1; i <= 16; i++) {
        var resistenciaCelda = resistenciaCeldas['r_cell_' + i];
        var elResistenciaCelda = document.getElementById('celda-res-' + i);
        if (resistenciaCelda != null) { elResistenciaCelda.textContent = (resistenciaCelda * 1000).toFixed(1); elResistenciaCelda.className = 'ci-v'; }
        else { elResistenciaCelda.textContent = '—'; elResistenciaCelda.className = 'ci-v'; }
      }

      updateMap(num(d.gps_lat), num(d.gps_lon));

      var voltajesCeldas = d.cells || {};
      var voltajeMax = -99, voltajeMin = 99, hayCeldas = false;
      for (var j = 1; j <= 16; j++) {
        var voltajeCelda = voltajesCeldas['cell_' + j];
        var elCelda = document.getElementById('cell_volts_' + j);
        if (voltajeCelda != null) {
          hayCeldas = true;
          if (voltajeCelda > voltajeMax) voltajeMax = voltajeCelda;
          if (voltajeCelda < voltajeMin) voltajeMin = voltajeCelda;
          elCelda.textContent = voltajeCelda.toFixed(3);
          elCelda.className = 'ci-v' + ((voltajeCelda < 3.0 || voltajeCelda > 3.65) ? ' w' : '');
        } else {
          elCelda.textContent = '—'; elCelda.className = 'ci-v';
        }
      }
      if (hayCeldas) {
        document.getElementById('celda-voltaje-max').textContent = voltajeMax.toFixed(3);
        document.getElementById('celda-voltaje-min').textContent = voltajeMin.toFixed(3);
        document.getElementById('celda-voltaje-delta').textContent = (voltajeMax - voltajeMin).toFixed(3);
      }

      var currDescarga = curr_p < 0 ? Math.abs(curr_p) : 0;
      var currRegen = curr_p > 0 ? curr_p : 0;
      var pHVval = (p_hv != null) ? p_hv : 0;
      var pRegenVal = (d.p_regen != null) ? d.p_regen : 0;

      var charts = FenixCharts;
      charts.push(charts.velocidad, 0, tms, speed_v); charts.push(charts.velocidad, 1, tms, rpm); charts.push(charts.velocidad, 2, tms, throttle);
      charts.push(charts.torquePotencia, 0, tms, torq); charts.push(charts.torquePotencia, 1, tms, p_mec); charts.push(charts.torquePotencia, 2, tms, pHVval);
      charts.push(charts.potenciaCorriente, 0, tms, pHVval); charts.push(charts.potenciaCorriente, 1, tms, currDescarga); charts.push(charts.potenciaCorriente, 2, tms, throttle);
      charts.push(charts.regen, 0, tms, pRegenVal); charts.push(charts.regen, 1, tms, brake); charts.push(charts.regen, 2, tms, currRegen);
      charts.velocidad.update('none'); charts.torquePotencia.update('none'); charts.potenciaCorriente.update('none'); charts.regen.update('none');

      var eta_total = (d.eta_total != null) ? d.eta_total : eta;
      drawPMRPM(rpm, p_mec, eta_total);
    } catch (e) {
      console.error('Error en updateDashboard:', e);
    }
  }

  window.updateDashboard = updateDashboard;
})();
