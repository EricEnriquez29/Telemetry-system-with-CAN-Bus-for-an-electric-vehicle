// ── Objeto 3D (Three.js) — pitch/roll del vehículo ──
// Solo updateHorizon se expone; la escena, cámara y modelo quedan privados.
(function () {
  var hzScene = new THREE.Scene();
  var hzCamera = new THREE.PerspectiveCamera(40, 150 / 120, 0.1, 100);
  hzCamera.position.set(3.2, 2.3, 3.8);
  hzCamera.lookAt(0, 0.25, 0);
  var hzRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  hzRenderer.setSize(150, 120);
  document.getElementById('horizonte-3d').appendChild(hzRenderer.domElement);

  var hzGroup = new THREE.Group();
  hzScene.add(hzGroup);

  (function buildKart() {
    var orangeMat = new THREE.MeshStandardMaterial({ color: 0xd85a30 });
    var darkMat = new THREE.MeshStandardMaterial({ color: 0x2c2c2a });
    var seatMat = new THREE.MeshStandardMaterial({ color: 0x444441 });
    var frameMat = new THREE.MeshStandardMaterial({ color: 0x999990, metalness: 0.7, roughness: 0.35 });

    var L = 2.2, W = 1.2, H = 0.1;

    var floorPan = new THREE.Mesh(new THREE.BoxGeometry(L, H, W), orangeMat);
    hzGroup.add(floorPan);

    var noseCover = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.16, W * 0.9), orangeMat);
    noseCover.position.set(L / 2 - 0.05, 0.13, 0);
    hzGroup.add(noseCover);

    var seatBack = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.55, 0.62), seatMat);
    seatBack.position.set(-0.35, 0.33, 0);
    hzGroup.add(seatBack);
    var seatBase = new THREE.Mesh(new THREE.BoxGeometry(0.62, 0.1, 0.62), seatMat);
    seatBase.position.set(0.0, 0.1, 0);
    hzGroup.add(seatBase);

    function tube(r, h) { return new THREE.CylinderGeometry(r, r, h, 10); }
    var TR = 0.03;

    var rearX = -0.75, frontX = 0.55, halfW = 0.55;
    var rearH = 0.85, frontH = 0.5;

    function addPost(x, z, h) {
      var p = new THREE.Mesh(tube(TR, h), frameMat);
      p.position.set(x, h / 2 + H / 2, z);
      hzGroup.add(p);
    }
    addPost(rearX, halfW, rearH);
    addPost(rearX, -halfW, rearH);
    addPost(frontX, halfW, frontH);
    addPost(frontX, -halfW, frontH);

    function addCrossBar(x, y, w) {
      var b = new THREE.Mesh(tube(TR, w), frameMat);
      b.rotation.x = Math.PI / 2;
      b.position.set(x, y, 0);
      hzGroup.add(b);
    }
    addCrossBar(rearX, rearH + H / 2, W * 0.92);
    addCrossBar(frontX, frontH + H / 2, W * 0.92);

    function diagBrace(x1, y1, z1, x2, y2, z2) {
      var dx = x2 - x1, dy = y2 - y1, dz = z2 - z1;
      var len = Math.sqrt(dx * dx + dy * dy + dz * dz);
      var m = new THREE.Mesh(tube(0.022, len), frameMat);
      m.position.set((x1 + x2) / 2, (y1 + y2) / 2, (z1 + z2) / 2);
      m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), new THREE.Vector3(dx, dy, dz).normalize());
      hzGroup.add(m);
    }
    diagBrace(rearX, rearH + H / 2, halfW, frontX, frontH + H / 2, halfW);
    diagBrace(rearX, rearH + H / 2, -halfW, frontX, frontH + H / 2, -halfW);
    diagBrace(rearX, rearH + H / 2, halfW, rearX, H / 2, -halfW);
    diagBrace(frontX, frontH + H / 2, halfW, frontX, H / 2, -halfW);

    var steer = new THREE.Mesh(new THREE.TorusGeometry(0.16, 0.018, 8, 16), darkMat);
    steer.rotation.x = Math.PI / 2.3;
    steer.position.set(0.4, 0.42, 0);
    hzGroup.add(steer);
    var steerCol = new THREE.Mesh(tube(0.025, 0.3), darkMat);
    steerCol.rotation.z = Math.PI / 2.6;
    steerCol.position.set(0.25, 0.28, 0);
    hzGroup.add(steerCol);

    var wheelR = 0.28;
    var wheelGeo = new THREE.CylinderGeometry(wheelR, wheelR, 0.2, 20);
    var wheelPositions = [[0.85, 0, 0.62], [0.85, 0, -0.62], [-0.85, 0, 0.62], [-0.85, 0, -0.62]];
    wheelPositions.forEach(function (p) {
      var wheel = new THREE.Mesh(wheelGeo, darkMat);
      wheel.rotation.x = Math.PI / 2;
      wheel.position.set(p[0], p[1], p[2]);
      hzGroup.add(wheel);
      var hub = new THREE.Mesh(tube(0.08, 0.22), frameMat);
      hub.rotation.x = Math.PI / 2;
      hub.position.set(p[0], p[1], p[2]);
      hzGroup.add(hub);
    });
  })();

  var hzGrid = new THREE.GridHelper(6, 12, 0x888880, 0x333330);
  hzScene.add(hzGrid);
  var hzAmbient = new THREE.AmbientLight(0xffffff, 0.75);
  hzScene.add(hzAmbient);
  var hzDir = new THREE.DirectionalLight(0xffffff, 0.6);
  hzDir.position.set(3, 5, 2);
  hzScene.add(hzDir);
  var hzFill = new THREE.DirectionalLight(0xffffff, 0.3);
  hzFill.position.set(-3, 2, -2);
  hzScene.add(hzFill);

  function updateHorizon(rollDeg, pitchDeg) {
    hzGroup.rotation.z = -rollDeg * Math.PI / 180;
    hzGroup.rotation.x = pitchDeg * Math.PI / 180;
    hzRenderer.render(hzScene, hzCamera);
    document.getElementById('horizonte-roll').textContent = rollDeg.toFixed(1) + '°';
    document.getElementById('horizonte-pitch').textContent = pitchDeg.toFixed(1) + '°';
  }
  updateHorizon(0, 0);

  window.updateHorizon = updateHorizon;
})();
