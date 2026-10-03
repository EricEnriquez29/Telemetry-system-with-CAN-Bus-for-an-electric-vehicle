// ── Menú lateral / cambio de pestañas ──
// Aislado en un IIFE: menuItems ya no vive en el scope global. Solo se
// exponen toggleMenu/closeMenu/switchTab porque el HTML las llama por
// onclick="...".
(function () {
  var menuItems = document.querySelectorAll('.menu-item');

  function toggleMenu() {
    document.getElementById('menu-drawer').classList.toggle('open');
    document.getElementById('menu-overlay').classList.toggle('open');
  }
  function closeMenu() {
    document.getElementById('menu-drawer').classList.remove('open');
    document.getElementById('menu-overlay').classList.remove('open');
  }
  function switchTab(i) {
    menuItems.forEach((t, j) => {
      t.classList.toggle('active', i === j);
      t.setAttribute('aria-selected', i === j ? 'true' : 'false');
      document.getElementById('tab-' + j).style.display = i === j ? 'block' : 'none';
    });
    // La pestaña de Ploteo construye sus gráficas la primera vez que se abre:
    // Plotly y Leaflet no pueden medir un contenedor que está en display:none.
    if (i === 2 && window.PloteoTab) window.PloteoTab.abrir();
    closeMenu();
  }

  window.toggleMenu = toggleMenu;
  window.closeMenu = closeMenu;
  window.switchTab = switchTab;
})();
