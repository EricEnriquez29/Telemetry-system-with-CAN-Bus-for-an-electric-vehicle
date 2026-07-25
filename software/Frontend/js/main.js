(function() {
  var cv  = document.getElementById('loading-canvas');
  var ctx = cv.getContext('2d');
  var t   = 0, raf;
  function drawLoader() {
    ctx.clearRect(0, 0, 150, 150);
    var cx = 75, cy = 75;
    ctx.beginPath();
    ctx.arc(cx, cy, 68, t, t + Math.PI * 1.5);
    ctx.strokeStyle = '#ef5e20';
    ctx.lineWidth = 3.5;
    ctx.lineCap = 'round';
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx, cy, 60, -t * 0.7, -t * 0.7 + Math.PI * 1.1);
    ctx.strokeStyle = '#ef5e20';
    ctx.lineWidth = 3;
    ctx.globalAlpha = 0.45;
    ctx.lineCap = 'round';
    ctx.stroke();
    ctx.globalAlpha = 1;
    t += 0.04;
    raf = requestAnimationFrame(drawLoader);
  }
  drawLoader();
  setTimeout(function() {
    cancelAnimationFrame(raf);
    var screen = document.getElementById('loading-screen');
    screen.style.transition = 'opacity 0.4s ease';
    screen.style.opacity = '0';
    setTimeout(function() { screen.style.display = 'none'; }, 400);
  }, 750);
})();

connect();
