// ── Mapa GPS (Leaflet) ──
// Se exponen centerMap (llamado por onclick en el HTML), updateMap y
// drawMetaLine (llamados por dashboard-render.js/meta-form.js). El resto
// (map, marker, metaLine...) queda privado dentro del IIFE.
(function () {
  var GPS_CENTER = [20.736972, -103.484194];
  var map = L.map('map', { zoomControl: true, attributionControl: false }).setView(GPS_CENTER, 18);
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 19 }).addTo(map);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png', { maxZoom: 19, opacity: 0.7 }).addTo(map);
  var marker = L.circleMarker(GPS_CENTER, { radius: 6, color: '#fff', fillColor: '#d9621a', fillOpacity: 1, weight: 2 }).addTo(map);

  function centerMap() { map.setView(marker.getLatLng(), map.getZoom(), { animate: true, duration: 0.5 }); }
  function updateMap(lat, lon) { if (lat === 0 && lon === 0) return; marker.setLatLng([lat, lon]); }

  var metaLine = null;
  var metaLineDrawn = null;
  function drawMetaLine(latA, lonA, latB, lonB) {
    if (latA == null || lonA == null || latB == null || lonB == null) return;
    var key = latA + ',' + lonA + ',' + latB + ',' + lonB;
    if (key === metaLineDrawn) return;
    metaLineDrawn = key;
    if (metaLine) map.removeLayer(metaLine);
    metaLine = L.polyline([[latA, lonA], [latB, lonB]], { color: '#000', weight: 3, opacity: 0.9 }).addTo(map);
  }

  window.centerMap = centerMap;
  window.updateMap = updateMap;
  window.drawMetaLine = drawMetaLine;
})();
