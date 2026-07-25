// ── Widgets dibujados a mano en Canvas 2D: batería, odómetro, contactor,
// G-meter, sag voltaje/corriente y potencia mecánica vs RPM ──
// Antes cada canvas/contexto/trail vivía suelto en el global; ahora quedan
// privados dentro del IIFE y solo se exponen las funciones draw* que
// dashboard-render.js necesita llamar en cada mensaje.
(function () {
  // ── Batería (barras) ──
  var battCv = document.getElementById('bateria-canvas'), battCtx = battCv.getContext('2d');
  var BATT_W = 122, BATT_H = 77, BATT_SCALE = 3;
  battCv.width = BATT_W * BATT_SCALE; battCv.height = BATT_H * BATT_SCALE;
  battCtx.scale(BATT_SCALE, BATT_SCALE);
  function drawBattery(percent) {
    var W = BATT_W, H = BATT_H;
    battCtx.clearRect(0, 0, W, H);
    var segments = 10;
    var x = 6, y = 10, w = W - 33, h = H - 34;
    var terminalW = 6, terminalH = h * 0.45;
    battCtx.strokeStyle = "#fff"; battCtx.lineWidth = 2.5;
    battCtx.beginPath(); battCtx.roundRect(x, y, w, h, 5); battCtx.stroke();
    battCtx.beginPath(); battCtx.roundRect(x + w, y + (h - terminalH) / 2, terminalW, terminalH, 2); battCtx.stroke();
    var innerPad = 4, gap = 1.5;
    var usableW = w - innerPad * 2 - gap * (segments - 1);
    var segW = usableW / segments;
    var active = Math.floor(percent / 10);
    var col = "#39FF14";
    for (var i = 0; i < segments; i++) {
      var sx = x + innerPad + i * (segW + gap), sy = y + innerPad, sh = h - innerPad * 2;
      if (i < active) {
        battCtx.fillStyle = col; battCtx.shadowColor = col; battCtx.shadowBlur = 6;
        battCtx.fillRect(sx, sy, segW, sh);
      } else {
        battCtx.shadowBlur = 0; battCtx.fillStyle = "#111";
        battCtx.fillRect(sx, sy, segW, sh);
      }
    }
    battCtx.shadowBlur = 0;
    battCtx.fillStyle = "#fff"; battCtx.font = "bold 17px Orbitron"; battCtx.textAlign = "center";
    battCtx.fillText(percent + "%", W / 2, H - 6);
  }
  drawBattery(0);

  // ── Odómetro (7 segmentos) ──
  var odoCv = document.getElementById('odo-canvas'), odoCtx = odoCv.getContext('2d');
  var ODO_W = 102, ODO_H = 31, ODO_SCALE = 3, ODO_DIGITS = 6;
  odoCv.width = ODO_W * ODO_SCALE; odoCv.height = ODO_H * ODO_SCALE;
  odoCtx.scale(ODO_SCALE, ODO_SCALE);
  var SEG_MAP = {
    '0': [1, 1, 1, 1, 1, 1, 0], '1': [0, 1, 1, 0, 0, 0, 0], '2': [1, 1, 0, 1, 1, 0, 1],
    '3': [1, 1, 1, 1, 0, 0, 1], '4': [0, 1, 1, 0, 0, 1, 1], '5': [1, 0, 1, 1, 0, 1, 1],
    '6': [1, 0, 1, 1, 1, 1, 1], '7': [1, 1, 1, 0, 0, 0, 0], '8': [1, 1, 1, 1, 1, 1, 1],
    '9': [1, 1, 1, 1, 0, 1, 1], ' ': [0, 0, 0, 0, 0, 0, 0]
  };
  function drawSeg(ctx, x, y, w, h, on, onColor, offColor) {
    var t = Math.max(2.2, w * 0.16);
    var p = t * 0.55;
    function hseg(cx, cy) {
      ctx.beginPath();
      ctx.moveTo(cx - w / 2 + p, cy);
      ctx.lineTo(cx - w / 2 + p + t / 1.2, cy - t / 2);
      ctx.lineTo(cx + w / 2 - p - t / 1.2, cy - t / 2);
      ctx.lineTo(cx + w / 2 - p, cy);
      ctx.lineTo(cx + w / 2 - p - t / 1.2, cy + t / 2);
      ctx.lineTo(cx - w / 2 + p + t / 1.2, cy + t / 2);
      ctx.closePath(); ctx.fill();
    }
    function vseg(cx, cy, half) {
      ctx.beginPath();
      ctx.moveTo(cx, cy - half + p);
      ctx.lineTo(cx - t / 2, cy - half + p + t / 1.2);
      ctx.lineTo(cx - t / 2, cy + half - p - t / 1.2);
      ctx.lineTo(cx, cy + half - p);
      ctx.lineTo(cx + t / 2, cy + half - p - t / 1.2);
      ctx.lineTo(cx + t / 2, cy - half + p + t / 1.2);
      ctx.closePath(); ctx.fill();
    }
    var cx = x + w / 2, halfH = (h - t) / 4;
    ctx.fillStyle = on[0] ? onColor : offColor; hseg(cx, y + t / 2);
    ctx.fillStyle = on[1] ? onColor : offColor; vseg(x + w - t / 2, y + h / 4 + t / 4, halfH);
    ctx.fillStyle = on[2] ? onColor : offColor; vseg(x + w - t / 2, y + 3 * h / 4 - t / 4, halfH);
    ctx.fillStyle = on[3] ? onColor : offColor; hseg(cx, y + h - t / 2);
    ctx.fillStyle = on[4] ? onColor : offColor; vseg(x + t / 2, y + 3 * h / 4 - t / 4, halfH);
    ctx.fillStyle = on[5] ? onColor : offColor; vseg(x + t / 2, y + h / 4 + t / 4, halfH);
    ctx.fillStyle = on[6] ? onColor : offColor; hseg(cx, y + h / 2);
  }
  function drawOdo(value) {
    var W = ODO_W, H = ODO_H;
    odoCtx.clearRect(0, 0, W, H);
    odoCtx.fillStyle = "#aaaaa0";
    odoCtx.beginPath(); odoCtx.roundRect(2, 2, W - 4, H - 4, 5); odoCtx.fill();
    odoCtx.strokeStyle = "#33332a"; odoCtx.lineWidth = 2;
    odoCtx.beginPath(); odoCtx.roundRect(2, 2, W - 4, H - 4, 5); odoCtx.stroke();
    var str = String(Math.floor(value)).padStart(ODO_DIGITS, '0');
    if (str.length > ODO_DIGITS) str = str.slice(-ODO_DIGITS);
    var padX = 10, dW = (W - padX * 2) / ODO_DIGITS, dH = H - 16;
    var dy = 8;
    var onCol = "#1a1a14", offCol = "#9a9a8e";
    for (var i = 0; i < ODO_DIGITS; i++) {
      var ch = str[i];
      var segs = SEG_MAP[ch] || SEG_MAP[' '];
      drawSeg(odoCtx, padX + i * dW + 2, dy, dW - 4, dH, segs, onCol, offCol);
    }
  }
  drawOdo(0);

  // ── Contactor ──
  var contCv = document.getElementById('contactor-canvas'), contCtx = contCv.getContext('2d');
  var CONT_SZ = 43, CONT_SCALE = 3;
  contCv.width = CONT_SZ * CONT_SCALE; contCv.height = CONT_SZ * CONT_SCALE;
  contCtx.scale(CONT_SCALE, CONT_SCALE);
  function drawContactor(cerrado) {
    var W = CONT_SZ, H = CONT_SZ, cx = W / 2, cy = H / 2;
    var R = W * 0.42, lw = W * 0.10, jR = W * 0.10, ijR = W * 0.045;
    contCtx.clearRect(0, 0, W, H);
    contCtx.beginPath(); contCtx.arc(cx, cy, R, 0, Math.PI * 2);
    contCtx.fillStyle = cerrado ? '#0052B4' : '#D30000'; contCtx.fill();
    contCtx.lineWidth = 2.5; contCtx.strokeStyle = '#fff'; contCtx.stroke();
    contCtx.lineWidth = lw; contCtx.strokeStyle = '#fff'; contCtx.lineCap = 'square';
    var armLen = R * 0.72;
    if (cerrado) {
      contCtx.beginPath(); contCtx.moveTo(cx, cy - armLen); contCtx.lineTo(cx, cy + armLen); contCtx.stroke();
    } else {
      contCtx.beginPath(); contCtx.moveTo(cx, cy - armLen); contCtx.lineTo(cx, cy - armLen * 0.45); contCtx.stroke();
      contCtx.beginPath(); contCtx.moveTo(cx, cy + armLen * 0.30); contCtx.lineTo(cx, cy + armLen); contCtx.stroke();
      contCtx.save(); contCtx.translate(cx, cy + armLen * 0.30); contCtx.rotate(-45 * Math.PI / 180);
      contCtx.beginPath(); contCtx.moveTo(0, 0); contCtx.lineTo(0, -armLen * 0.85); contCtx.stroke();
      contCtx.restore();
    }
    var jy = cerrado ? cy + armLen * 0.33 : cy + armLen * 0.30;
    contCtx.beginPath(); contCtx.arc(cx, jy, jR, 0, Math.PI * 2); contCtx.fillStyle = '#fff'; contCtx.fill();
    contCtx.beginPath(); contCtx.arc(cx, jy, ijR, 0, Math.PI * 2); contCtx.fillStyle = cerrado ? '#0052B4' : '#D30000'; contCtx.fill();
  }
  drawContactor(true);

  // ── G-meter ──
  var gmCv = document.getElementById('gmeter-canvas'), gmCtx = gmCv.getContext('2d');
  var GM_SZ = 150, GM_SCALE = 3, GM_GMAX = 2.0;
  gmCv.width = GM_SZ * GM_SCALE; gmCv.height = GM_SZ * GM_SCALE; gmCtx.scale(GM_SCALE, GM_SCALE);
  var gmTrail = [];
  function drawGMeter(gx, gy) {
    var W = GM_SZ, H = GM_SZ, cx = W / 2, cy = H / 2, R = W / 2 - 10;
    gmCtx.clearRect(0, 0, W, H);
    gmCtx.strokeStyle = '#1a1a1a'; gmCtx.lineWidth = 1;
    for (var r = 1; r <= 2; r++) {
      gmCtx.beginPath(); gmCtx.arc(cx, cy, R * r / 2, 0, Math.PI * 2); gmCtx.stroke();
    }
    gmCtx.beginPath(); gmCtx.moveTo(cx - R, cy); gmCtx.lineTo(cx + R, cy);
    gmCtx.moveTo(cx, cy - R); gmCtx.lineTo(cx, cy + R); gmCtx.stroke();
    gmCtx.fillStyle = '#999'; gmCtx.font = '7px Share Tech Mono'; gmCtx.textAlign = 'center';
    gmCtx.fillText('ACEL', cx, cy - R - 2); gmCtx.fillText('FRENO', cx, cy + R + 7);
    gmCtx.textAlign = 'left'; gmCtx.fillText('DER', cx + R - 12, cy - 3);
    gmCtx.textAlign = 'right'; gmCtx.fillText('IZQ', cx - R + 12, cy - 3);
    var px = cx + (gy / GM_GMAX) * R, py = cy - (gx / GM_GMAX) * R;
    px = Math.max(cx - R, Math.min(cx + R, px)); py = Math.max(cy - R, Math.min(cy + R, py));
    gmTrail.push([px, py]); if (gmTrail.length > 15) gmTrail.shift();
    for (var i = 0; i < gmTrail.length; i++) {
      var a = i / gmTrail.length;
      gmCtx.beginPath(); gmCtx.arc(gmTrail[i][0], gmTrail[i][1], 2, 0, Math.PI * 2);
      gmCtx.fillStyle = 'rgba(58,168,189,' + (a * 0.4) + ')'; gmCtx.fill();
    }
    gmCtx.beginPath(); gmCtx.arc(px, py, 5, 0, Math.PI * 2);
    gmCtx.fillStyle = '#3aa8bd'; gmCtx.shadowColor = '#3aa8bd'; gmCtx.shadowBlur = 8; gmCtx.fill(); gmCtx.shadowBlur = 0;
  }
  drawGMeter(0, 0);

  // ── Sag: voltaje vs corriente ──
  var sagCv = document.getElementById('sag-canvas'), sagCtx = sagCv.getContext('2d');
  var SAG_SZ = 150, SAG_SCALE = 3;
  var SAG_VMIN = 40, SAG_VMAX = 60, SAG_IMAX = 200;
  sagCv.width = SAG_SZ * SAG_SCALE; sagCv.height = SAG_SZ * SAG_SCALE; sagCtx.scale(SAG_SCALE, SAG_SCALE);
  var sagTrail = [];
  function drawSag(volt, curr) {
    var W = SAG_SZ, H = SAG_SZ, pad = 22;
    sagCtx.clearRect(0, 0, W, H);
    sagCtx.strokeStyle = '#1a1a1a'; sagCtx.lineWidth = 1;
    sagCtx.beginPath(); sagCtx.moveTo(pad, 5); sagCtx.lineTo(pad, H - pad); sagCtx.lineTo(W - 5, H - pad); sagCtx.stroke();
    sagCtx.fillStyle = '#999'; sagCtx.font = '7px Share Tech Mono';
    sagCtx.textAlign = 'right';
    sagCtx.fillText(SAG_VMAX + 'V', pad - 2, 12); sagCtx.fillText(SAG_VMIN + 'V', pad - 2, H - pad);
    sagCtx.textAlign = 'center';
    sagCtx.fillText('0', pad, H - pad + 9); sagCtx.fillText(SAG_IMAX + 'A', W - 12, H - pad + 9);
    sagCtx.save(); sagCtx.translate(8, H / 2); sagCtx.rotate(-Math.PI / 2); sagCtx.fillText('Voltaje', 0, 0); sagCtx.restore();
    sagCtx.fillText('Corriente', (pad + W) / 2, H - 4);
    var ix = Math.abs(curr) / SAG_IMAX, vy = (volt - SAG_VMIN) / (SAG_VMAX - SAG_VMIN);
    ix = Math.max(0, Math.min(1, ix)); vy = Math.max(0, Math.min(1, vy));
    var px = pad + ix * (W - 5 - pad), py = (H - pad) - vy * (H - pad - 5);
    sagTrail.push([px, py]); if (sagTrail.length > 20) sagTrail.shift();
    sagCtx.strokeStyle = 'rgba(194,168,56,0.3)'; sagCtx.lineWidth = 1; sagCtx.beginPath();
    for (var i = 0; i < sagTrail.length; i++) { if (i === 0) sagCtx.moveTo(sagTrail[i][0], sagTrail[i][1]); else sagCtx.lineTo(sagTrail[i][0], sagTrail[i][1]); }
    sagCtx.stroke();
    var col = vy > 0.7 ? '#3ba776' : vy > 0.4 ? '#c2a838' : '#cc4055';
    sagCtx.beginPath(); sagCtx.arc(px, py, 5, 0, Math.PI * 2);
    sagCtx.fillStyle = col; sagCtx.shadowColor = col; sagCtx.shadowBlur = 8; sagCtx.fill(); sagCtx.shadowBlur = 0;
  }
  drawSag(SAG_VMAX, 0);

  // ── Potencia mecánica vs RPM (color = eficiencia TME) ──
  var pmCv = document.getElementById('canvas-potencia-rpm'), pmCtx = pmCv.getContext('2d');
  var PM_SCALE = 3, PM_RPMMAX = 5000, PM_PMAX = 6000;
  var pmW = 0, pmH = 0;
  function pmResize() {
    var r = pmCv.getBoundingClientRect();
    pmW = r.width || 400; pmH = r.height || 220;
    pmCv.width = pmW * PM_SCALE; pmCv.height = pmH * PM_SCALE;
    pmCtx.setTransform(PM_SCALE, 0, 0, PM_SCALE, 0, 0);
  }
  function etaColor(eta) {
    if (eta == null) return '#555';
    var t = Math.max(0, Math.min(1, (eta - 60) / 40));
    var stops = [[0, [34, 102, 204]], [0.4, [59, 167, 118]], [0.7, [194, 168, 56]], [1, [204, 64, 85]]];
    for (var i = 0; i < stops.length - 1; i++) {
      if (t >= stops[i][0] && t <= stops[i + 1][0]) {
        var f = (t - stops[i][0]) / (stops[i + 1][0] - stops[i][0]);
        var c0 = stops[i][1], c1 = stops[i + 1][1];
        var r = Math.round(c0[0] + (c1[0] - c0[0]) * f);
        var g = Math.round(c0[1] + (c1[1] - c0[1]) * f);
        var b = Math.round(c0[2] + (c1[2] - c0[2]) * f);
        return 'rgb(' + r + ',' + g + ',' + b + ')';
      }
    }
    return '#cc4055';
  }
  var pmTrail = [];
  function drawPMRPM(rpm, pmec, eta) {
    if (pmW === 0) pmResize();
    var W = pmW, H = pmH, pad = 30;
    pmCtx.clearRect(0, 0, W, H);
    pmCtx.strokeStyle = '#1a1a1a'; pmCtx.lineWidth = 1;
    pmCtx.beginPath(); pmCtx.moveTo(pad, 8); pmCtx.lineTo(pad, H - pad); pmCtx.lineTo(W - 8, H - pad); pmCtx.stroke();
    pmCtx.fillStyle = '#999'; pmCtx.font = '8px Share Tech Mono';
    pmCtx.textAlign = 'right';
    for (var p = 0; p <= PM_PMAX; p += 2000) { var y = (H - pad) - (p / PM_PMAX) * (H - pad - 8); pmCtx.fillText(p + '', pad - 3, y + 3); }
    pmCtx.textAlign = 'center';
    for (var r = 0; r <= PM_RPMMAX; r += 1000) { var x = pad + (r / PM_RPMMAX) * (W - 8 - pad); pmCtx.fillText(r + '', x, H - pad + 10); }
    pmCtx.fillText('RPM', (pad + W) / 2, H - 4);
    pmCtx.save(); pmCtx.translate(9, H / 2); pmCtx.rotate(-Math.PI / 2); pmCtx.fillText('P.Mec (W)', 0, 0); pmCtx.restore();
    var px = pad + (Math.min(rpm, PM_RPMMAX) / PM_RPMMAX) * (W - 8 - pad);
    var py = (H - pad) - (Math.min(pmec, PM_PMAX) / PM_PMAX) * (H - pad - 8);
    pmTrail.push([px, py, eta]); if (pmTrail.length > 25) pmTrail.shift();
    for (var i = 0; i < pmTrail.length; i++) {
      var a = i / pmTrail.length * 0.5;
      pmCtx.beginPath(); pmCtx.arc(pmTrail[i][0], pmTrail[i][1], 3, 0, Math.PI * 2);
      var c = etaColor(pmTrail[i][2]);
      pmCtx.fillStyle = c.replace('rgb', 'rgba').replace(')', ',' + a + ')');
      pmCtx.fill();
    }
    var col = etaColor(eta);
    pmCtx.beginPath(); pmCtx.arc(px, py, 7, 0, Math.PI * 2);
    pmCtx.fillStyle = col; pmCtx.shadowColor = col; pmCtx.shadowBlur = 10; pmCtx.fill(); pmCtx.shadowBlur = 0;
  }
  setTimeout(pmResize, 100);
  window.addEventListener('resize', pmResize);

  window.drawBattery = drawBattery;
  window.drawOdo = drawOdo;
  window.drawContactor = drawContactor;
  window.drawGMeter = drawGMeter;
  window.drawSag = drawSag;
  window.drawPMRPM = drawPMRPM;
})();
