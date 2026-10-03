// ── Pestaña de Ploteo: análisis de sesiones y gráfica en vivo ──
//
// Portado del prototipo demo-ploteo.html de la raíz del repo, que es donde se
// diseñó y se probó esta pantalla. Lo único que cambia al traerlo aquí es de
// dónde salen los datos:
//
//   histórico → GET /session_series (backend_core/historicos.py)
//   en vivo   → el mismo WebSocket que alimenta el dashboard
//
// El demo sigue en el repo como banco de pruebas: se puede abrir sin backend,
// con datos simulados, para probar cambios de la gráfica sin tocar el servidor.
//
// Va en un IIFE y solo expone PloteoVivo (para que dashboard-render.js le pase
// cada snapshot) y PloteoTab (para que el menú avise al entrar a la pestaña).
(function () {
'use strict';

// El campo `min` es el mínimo FÍSICAMENTE posible. El MGT usa -1 como marca de
// "sin dato" en las variables que vienen del bus CAN, y sin esta declaración
// esos -1 se dibujan como mediciones: una velocidad de -1 km/h estira el eje,
// falsea los promedios y colorea el mapa con un valor que nunca ocurrió.
// Solo se declara donde el mínimo es indiscutible: la corriente del paquete y
// las fuerzas G sí pueden ser negativas, así que se dejan sin filtro.
// `dec` son los decimales con los que tiene sentido leer cada variable. La
// base devuelve flotantes crudos —42.199999999999996 km/h— y mostrarlos tal
// cual llena la tabla de dígitos que no significan nada.
var VARIABLES = [
  {id:'speed_v', nombre:'Velocidad',        unidad:'km/h', min:0, dec:1},
  {id:'rpm',     nombre:'RPM',              unidad:'rpm',  min:0, dec:0},
  {id:'p_hv',    nombre:'Potencia HV',      unidad:'W',    min:0, dec:0},
  {id:'p_mec',   nombre:'Potencia mecánica',unidad:'W',    min:0, dec:0},
  {id:'curr_p',  nombre:'Corriente pack',   unidad:'A',           dec:1},
  {id:'throttle',nombre:'Acelerador',       unidad:'%',    min:0, dec:0},
  {id:'brake',   nombre:'Freno',            unidad:'%',    min:0, dec:0},
  {id:'Gx',      nombre:'G longitudinal',   unidad:'G',           dec:2},
  {id:'Gy',      nombre:'G lateral',        unidad:'G',           dec:2},
  {id:'E_HV',    nombre:'Energía consumida',unidad:'Wh',   min:0, dec:2},
  {id:'eta',     nombre:'Eficiencia motor', unidad:'%',    min:0, dec:1},
  {id:'soc',     nombre:'SOC',              unidad:'%',    min:0, dec:1}
];
// Nombres neutros a propósito: en una vuelta suelta son tiempo y distancia DE
// LA VUELTA, pero en una sesión completa están acumulados sobre todas las
// vueltas. Llamarlos "de vuelta" haría leer 193 s como si fuera una vuelta.
var EJES_X = [
  {id:'t_vuelta', nombre:'Tiempo transcurrido',  unidad:'s', dec:1},
  // Integral de la velocidad: el recorrido REAL del coche. Sirve para
  // consumo por metro, para medir el largo de una trazada y para saber
  // cuánto rodó. NO sirve para comparar vueltas: el error de cada curva se
  // acumula hasta la meta, así que a mitad de vuelta enfrenta puntos de
  // pista distintos.
  {id:'d_vuelta', nombre:'Distancia recorrida',  unidad:'m', dec:0}
].concat(VARIABLES);

// Ejes que representan el avance por la vuelta. Contra ellos las muestras
// forman una serie ordenada y se dibujan como línea; contra cualquier otra
// variable son una nube de puntos.
function esEjeDeRecorrido(id){
  return id === 't_vuelta' || id === 'd_vuelta';
}


var M_LAT = 111320;
function mLon(lat){ return 111320*Math.cos(lat*Math.PI/180); }
function aMetros(p, ref){
  return {x:(p.lon - ref.lon)*mLon(ref.lat), y:(p.lat - ref.lat)*M_LAT};
}
function distanciaGeo(a, b){
  var lm = (a.lat + b.lat)/2;
  var dx = (a.lon - b.lon)*mLon(lm), dy = (a.lat - b.lat)*M_LAT;
  return Math.sqrt(dx*dx + dy*dy);
}

var COLORES = ['#ef5e20','#3aa8bd','#a85cc0'];
// En nube de puntos no se dibujan líneas, así que el tipo de trazo no
// distingue nada: la variable se identifica por la forma del marcador
var SIMBOLOS = ['circle','square','triangle-up'];
var MAX_Y = 3, MAX_ORIGENES = 3;
var VENTANA_S = 20;


// ═════════════════════════════════════════════════════════════════════
//  LOS DATOS
//
//  Una sesión se pide entera, una sola vez, y se guarda en memoria. Pedir
//  vuelta por vuelta sería una consulta a InfluxDB por cada cambio del
//  selector, y comparar tres vueltas de la misma tanda es justo lo normal.
// ═════════════════════════════════════════════════════════════════════
var SERIES = {};      // "fecha|sesion" → {vueltas:[], porVuelta:{}, completa:[]}
var PETICIONES = {};  // peticiones en vuelo, para no pedir dos veces lo mismo
var SESIONES_DIA = {};

function claveSerie(fecha, sesion){ return fecha + '|' + sesion; }
function serieDe(fecha, sesion){ return SERIES[claveSerie(fecha, sesion)] || null; }

function urlSerie(fecha, sesion){
  return FenixConfig.sessionSeriesUrl +
    '?date=' + encodeURIComponent(fecha) +
    '&session_id=' + encodeURIComponent(sesion) +
    '&fields=' + VARIABLES.map(function(v){ return v.id; }).join(',');
}

// Agrupa las muestras por vuelta y arma también la sesión completa, con el
// tiempo y la distancia acumulados vuelta tras vuelta. El backend devuelve
// t_vuelta y d_vuelta tal como se registraron, es decir reiniciados en cada
// cruce de meta; sin acumular, la sesión entera se dibujaría encimada sobre
// los mismos veinte segundos.
function armarSerie(json){
  var porVuelta = {}, vueltas = json.vueltas || [];
  (json.muestras || []).forEach(function(m){
    (porVuelta[m.n_vuelta] = porVuelta[m.n_vuelta] || []).push(m);
  });
  var completa = [], despT = 0, despD = 0;
  vueltas.forEach(function(v){
    var lv = porVuelta[v] || [];
    if (!lv.length) return;
    lv.forEach(function(p){
      var q = Object.assign({}, p);
      q.t_vuelta = +((q.t_vuelta || 0) + despT).toFixed(1);
      q.d_vuelta = +((q.d_vuelta || 0) + despD).toFixed(1);
      completa.push(q);
    });
    despT += lv[lv.length-1].t_vuelta || 0;
    despD += lv[lv.length-1].d_vuelta || 0;
  });
  return {vueltas: vueltas, porVuelta: porVuelta, completa: completa,
          paso: json.paso || 1, n: json.n_muestras || 0};
}

function cargarSerie(fecha, sesion){
  var k = claveSerie(fecha, sesion);
  if (SERIES[k]) return Promise.resolve(SERIES[k]);
  if (PETICIONES[k]) return PETICIONES[k];
  PETICIONES[k] = fetch(urlSerie(fecha, sesion), {cache:'no-store'})
    .then(function(r){ return r.json(); })
    .then(function(j){
      if (j.error) throw new Error(j.error);
      SERIES[k] = armarSerie(j);
      delete PETICIONES[k];
      return SERIES[k];
    })
    .catch(function(e){ delete PETICIONES[k]; throw e; });
  return PETICIONES[k];
}

function cargarSesionesDe(fecha){
  if (SESIONES_DIA[fecha]) return Promise.resolve(SESIONES_DIA[fecha]);
  return fetch(FenixConfig.sessionsForDateUrl + '?date=' + encodeURIComponent(fecha), {cache:'no-store'})
    .then(function(r){ return r.json(); })
    .then(function(j){ SESIONES_DIA[fecha] = j.sessions || []; return SESIONES_DIA[fecha]; })
    .catch(function(){ return []; });
}

function datosVuelta(fecha, sesion, vuelta){
  var s = serieDe(fecha, sesion);
  return (s && s.porVuelta[vuelta]) ? s.porVuelta[vuelta] : [];
}
function datosSesion(fecha, sesion){
  var s = serieDe(fecha, sesion);
  return s ? s.completa : [];
}

function estado(txt, clase){
  var el = document.getElementById('h-estado');
  if (!el) return;
  el.textContent = txt || '';
  el.className = 'pl-estado-carga' + (clase ? ' ' + clase : '');
}

function meta(id){ return EJES_X.concat(VARIABLES).find(function(v){return v.id===id;}) || {nombre:id,unidad:''}; }
function llenarSelect(sel, lista, valor){
  sel.innerHTML = '';
  lista.forEach(function(v){
    var o = document.createElement('option');
    o.value = v.id; o.textContent = v.nombre + (v.unidad ? ' ['+v.unidad+']' : '');
    sel.appendChild(o);
  });
  if (valor) sel.value = valor;
}
function opcion(sel, valor, texto){
  var o = document.createElement('option'); o.value = valor; o.textContent = texto;
  sel.appendChild(o); return o;
}

function construirLista(cont, marcadas, alCambiar){
  cont.innerHTML = '';
  VARIABLES.forEach(function(v){
    var lab = document.createElement('label');
    lab.className = 'chk-item';
    lab.innerHTML = '<input type="checkbox" value="'+v.id+'"><span>'+v.nombre+'</span><span class="u">'+v.unidad+'</span>';
    var chk = lab.querySelector('input');
    chk.checked = marcadas.indexOf(v.id) >= 0;
    chk.onchange = function(){
      if (chk.checked && marcadasDe(cont).length > MAX_Y){ chk.checked = false; return; }
      pintarLista(cont); alCambiar();
    };
    cont.appendChild(lab);
  });
  pintarLista(cont);
}
function marcadasDe(cont){
  return Array.prototype.slice.call(cont.querySelectorAll('input:checked')).map(function(c){return c.value;});
}
function pintarLista(cont){
  var n = marcadasDe(cont).length, tope = n >= MAX_Y;
  cont.querySelectorAll('.chk-item').forEach(function(it){
    var c = it.querySelector('input');
    it.classList.toggle('sel', c.checked);
    it.classList.toggle('bloq', tope && !c.checked);
    c.disabled = tope && !c.checked;
  });
  var cuenta = document.getElementById(cont.id + '-cuenta');
  if (cuenta) cuenta.textContent = n + ' de ' + MAX_Y + ' seleccionadas';
}

var LAYOUT_BASE = {
  paper_bgcolor:'#0d0d0d', plot_bgcolor:'#0d0d0d',
  font:{family:'Share Tech Mono, monospace', color:'#b0b0b0', size:10},
  margin:{l:56,r:56,t:10,b:42},
  showlegend:true, legend:{orientation:'h', y:1.13, font:{size:9}},
  dragmode:false               // sin zoom por selección ni arrastre
};
// Con tres variables, el tercer eje tiene que apartarse: si se deja en 'left'
// sin desplazar, se dibuja justo encima del primero y los dos rótulos se pisan.
// `fijo` bloquea el eje. En vivo tiene que estar bloqueado —la gráfica se
// redibuja diez veces por segundo y cualquier zoom se perderia en el acto—,
// pero en el histórico los datos no se mueven y ampliar una curva concreta es
// justo lo que hace falta para analizar.
// Marcas del eje Y con dos extra, en los extremos que la señal alcanzó de
// verdad. Sin ellas hay que interpolar a ojo entre dos rayas: con divisiones de
// diez en diez y una punta de 63.7 km/h, el eje dice 60 y 70 y el dato exacto no
// aparece en ninguna parte.
//
// Se marcan los DOS extremos y no solo el alto, porque en una variable con
// signo el pico está en el otro lado: la corriente de pack es negativa toda la
// vuelta, y su máximo, −40 A, es el momento de menos demanda. El pico de
// verdad, −120 A, es el mínimo.
//
// Una marca de extremo desplaza a la regular que le quede demasiado cerca, o se
// solaparían las dos etiquetas y no se leería ninguna.
function ticksConExtremos(lo, hi, vmin, vmax, dec){
  var rango = hi - lo;
  if (!(rango > 0)) return null;
  var extra = [vmin, vmax].filter(function(v){ return v !== null && v !== undefined && isFinite(v); });
  if (!extra.length) return null;
  // Con la señal casi plana los dos extremos caen encima: sobra con uno
  if (extra.length === 2 && Math.abs(extra[1] - extra[0]) < rango*0.05) extra = [extra[1]];

  var crudo = rango/5;
  var pot = Math.pow(10, Math.floor(Math.log10(crudo)));
  var mult = 10;
  [1, 2, 2.5, 5, 10].some(function(x){ if (crudo <= pot*x){ mult = x; return true; } return false; });
  var paso = pot*mult;
  var vals = [];
  for (var t = Math.ceil(lo/paso)*paso; t <= hi + paso*1e-6; t += paso) vals.push(+t.toFixed(10));
  vals = vals.filter(function(t){
    return extra.every(function(v){ return Math.abs(t - v) > rango*0.05; });
  });
  vals = vals.concat(extra);
  vals.sort(function(a, b){ return a - b; });
  var d = (dec !== undefined) ? dec : 2;
  return {tickvals: vals, ticktext: vals.map(function(t){ return t.toFixed(d); })};
}

// Nombre del eje de la franja k, contando desde arriba. Plotly numera los ejes
// de abajo hacia arriba, así que la franja de arriba es el eje de mayor índice.
function ejeDeFranja(k){ return k === 0 ? 'y' : 'y' + (k+1); }
// Alto que ocupa cada franja, con un hueco entre ellas para que no se toquen
function dominioFranja(k, total){
  var hueco = 0.06, alto = (1 - hueco*(total-1)) / total;
  var arriba = 1 - k*(alto + hueco);
  return [+(arriba - alto).toFixed(4), +arriba.toFixed(4)];
}

function ejeY(k, etiqueta, color, campo, fijo, rango, vmin, vmax){
  var m = campo ? meta(campo) : {};
  var e = {title:{text:etiqueta,font:{size:9,color:color}}, gridcolor:'#1a1a1a',
           zerolinecolor:'#222', tickfont:{color:color}, fixedrange:(fijo !== false),
           hoverformat: '.'+(m.dec !== undefined ? m.dec : 2)+'f'};
  if (rango){ e.range = rango.slice(); e.autorange = false; }
  if (vmax !== undefined && vmax !== null && isFinite(vmax)){
    var lo = rango ? rango[0] : vmin, hi = rango ? rango[1] : vmax;
    var tk = ticksConExtremos(lo, hi, vmin, vmax, m.dec);
    if (tk){ e.tickmode = 'array'; e.tickvals = tk.tickvals; e.ticktext = tk.ticktext; }
  }
  if (k===1){ e.overlaying='y'; e.side='right'; }
  if (k===2){ e.overlaying='y'; e.side='left'; e.anchor='free'; e.position=0; }
  return e;
}

// Índice del punto cuyo eje X está más cerca del valor buscado.
// El cursor NO puede alinearse por posición en el arreglo: dos vueltas tienen
// distinto número de muestras, así que el punto 200 de una está en un metro
// distinto que el 200 de la otra, y la comparación dejaría de tener sentido.
// Devuelve null si el valor cae fuera del recorrido de ese origen. Sin esa
// comprobación, al comparar una vuelta de 0.37 km con una sesión de 2.2 km y
// poner el cursor en el km 1.5, la vuelta devolvía su último punto —a 1.1 km
// de distancia— como si fuera un valor comparable.
function indiceMasCercano(datos, campoX, valorX){
  var min = Infinity, max = -Infinity;
  for (var i=0;i<datos.length;i++){
    var v = datos[i][campoX];
    if (v < min) min = v;
    if (v > max) max = v;
  }
  // La tolerancia no puede ser un porcentaje del recorrido: daba 4 m en una
  // vuelta y 22 m en una sesión completa, así que un punto a 22 metros se
  // presentaba como si estuviera alineado. Se deriva del paso real entre
  // muestras, que es lo que fija la resolución de la comparación.
  var paso = (max - min) / Math.max(1, datos.length - 1);
  var margen = paso * 3;
  if (valorX < min - margen || valorX > max + margen) return null;

  // Tiempo y distancia siempre crecen dentro de un origen, así que se puede
  // buscar por bisección: con tres sesiones completas cargadas, recorrer los
  // arreglos enteros en cada movimiento del ratón son ~17 000 comparaciones,
  // frente a ~13 por bisección.
  var izq = 0, der = datos.length - 1;
  while (der - izq > 1){
    var medio = (izq + der) >> 1;
    if (datos[medio][campoX] <= valorX) izq = medio; else der = medio;
  }
  return (Math.abs(datos[izq][campoX] - valorX) <= Math.abs(datos[der][campoX] - valorX)) ? izq : der;
}
// Los datos reales traen huecos: campos condicionales que llegan nulos, cortes
// de GPS, y muestras perdidas por una reconexión. Nada de eso debe romper la
// herramienta ni, peor, dibujarse como si fuera un valor medido.
function coordValida(p){
  return p && typeof p.lat === 'number' && typeof p.lon === 'number' &&
         isFinite(p.lat) && isFinite(p.lon) &&
         !(p.lat === 0 && p.lon === 0);   // 0,0 es el clásico "sin fijación GPS"
}
function valorValido(v){ return v !== null && v !== undefined && isFinite(v); }

// Devuelve el valor, o null si no es medible: nulo, no numérico, o por debajo
// del mínimo físico de esa variable (el -1 que el MGT usa como "sin dato").
function formatear(v, campo){
  if (v === null || v === undefined || !isFinite(v)) return '—';
  var m = meta(campo);
  return v.toFixed(m.dec !== undefined ? m.dec : 2);
}

function sano(punto, campo){
  if (!punto) return null;
  var v = punto[campo];
  if (!valorValido(v)) return null;
  var m = meta(campo);
  if (m.min !== undefined && v < m.min) return null;
  return v;
}

// Diez tonos de azul a rojo, tomados de la paleta Turbo: azul, celeste,
// turquesa, verde, lima, amarillo, ámbar, naranja, rojo y rojo oscuro. Cada
// tramo de la barra cambia de tono, no solo de intensidad, así que en el mapa se
// separan bien zonas con pocos km/h de diferencia. Se recortan los extremos de
// Turbo, que son casi negros y se perderían sobre la foto de satélite.
var PARADAS_COLOR = [
  [0.000, [ 70, 107, 227]],
  [0.111, [ 40, 187, 236]],
  [0.222, [ 26, 228, 182]],
  [0.333, [100, 253, 106]],
  [0.444, [164, 252,  60]],
  [0.556, [225, 221,  55]],
  [0.667, [254, 174,  45]],
  [0.778, [246, 111,  26]],
  [0.889, [212,  52,   5]],
  [1.000, [165,  20,   3]]
];
function escalaColor(f){
  f = Math.max(0, Math.min(1, f));
  for (var k=1; k<PARADAS_COLOR.length; k++){
    if (f <= PARADAS_COLOR[k][0]){
      var p0 = PARADAS_COLOR[k-1], p1 = PARADAS_COLOR[k];
      var u = (f - p0[0]) / (p1[0] - p0[0]), a = p0[1], b = p1[1];
      return 'rgb('+Math.round(a[0]+(b[0]-a[0])*u)+','+Math.round(a[1]+(b[1]-a[1])*u)+','+Math.round(a[2]+(b[2]-a[2])*u)+')';
    }
  }
  var c = PARADAS_COLOR[PARADAS_COLOR.length-1][1];
  return 'rgb('+c[0]+','+c[1]+','+c[2]+')';
}

// En vivo: gráfica totalmente estática.
// Mismo trato que el histórico: rueda para acercar, arrastrar para moverse,
// doble clic para volver. staticPlot lo desactivaría todo.
var CONFIG_VIVO = {displayModeBar:false, responsive:true, scrollZoom:true, doubleClick:'reset'};
// Histórico: con zoom, y conservando el cursor. staticPlot desactivaría ambos
// y con ellos la sincronización con el mapa, así que se configura a mano.
// Rueda para acercar, arrastrar para moverse, doble clic para volver a la
// vista completa. Sin barra de herramientas: eso lo cubre todo.
var CONFIG_HIST = {displayModeBar:false, responsive:true, scrollZoom:true, doubleClick:'reset'};


// ═════════════════════════════════════════════════════════════════════
//  EN VIVO
// ═════════════════════════════════════════════════════════════════════
// `zoom` guarda la vista que puso el usuario. Sin esto el zoom en vivo sería
// inútil: la gráfica se redibuja diez veces por segundo y cada redibujo
// devolvería el eje a la ventana deslizante antes de que diera tiempo a mirar.
// Mientras hay zoom, la vista se queda quieta y los datos siguen entrando;
// el doble clic la suelta y vuelve a seguir al coche.
var vivo = {buffer:[], vuelta:0, corriendo:true, zoom:null, ultimo:0, pintar:false};

function inicializarVivo(){
  llenarSelect(document.getElementById('v-x'), EJES_X, 't_vuelta');
  construirLista(document.getElementById('v-y'), ['speed_v','p_hv','throttle'], redibujarVivo);
  document.getElementById('v-x').onchange = redibujarVivo;
  document.getElementById('v-toggle').onclick = function(){
    vivo.corriendo = !vivo.corriendo;
    this.textContent = vivo.corriendo ? 'Pausar' : 'Reanudar';
    document.getElementById('v-dot').className = vivo.corriendo ? 'pl-dot' : 'pl-dot off';
    document.getElementById('v-estado').textContent = vivo.corriendo ? 'Recibiendo' : 'Gráfica pausada';
  };
  Plotly.newPlot('g-vivo', [], JSON.parse(JSON.stringify(LAYOUT_BASE)), CONFIG_VIVO);
  // Plotly emite plotly_relayout también cuando la gráfica se redibuja sola, no
  // solo cuando el usuario toca. Sin distinguirlo, el primer redibujo se
  // guardaba como si fuera un zoom y la vista se quedaba congelada en los
  // primeros datos para el resto de la sesión.
  var gv = document.getElementById('g-vivo'), ultimoToque = 0;
  ['wheel','mousedown','touchstart','dblclick'].forEach(function(t){
    gv.addEventListener(t, function(){ ultimoToque = Date.now(); }, true);
  });
  gv.on('plotly_relayout', function(ev){
    if (Date.now() - ultimoToque > 1000) return;   // vino del redibujo, no del ratón
    // El doble clic manda autorange:true en todos los ejes — eso suelta la vista
    var suelta = Object.keys(ev).some(function(k){ return /autorange$/.test(k) && ev[k] === true; });
    if (suelta || ev.dragmode){ vivo.zoom = null; return; }
    var z = {}, hay = false;
    Object.keys(gv.layout).forEach(function(k){
      if (!/^[xy]axis/.test(k) || !gv.layout[k].range) return;
      z[k] = gv.layout[k].range.slice(); hay = true;
    });
    if (hay) vivo.zoom = z;
  });
  // Un redibujo por cada mensaje serían diez por segundo contra una gráfica de
  // tres franjas, con el dashboard entero dibujándose a la vez. Se acumula y se
  // pinta a ritmo de pantalla.
  setInterval(function(){
    if (!vivo.pintar) return;
    vivo.pintar = false;
    if (panelActivo() === 'vivo') redibujarVivo();
  }, 100);
}

// Cada snapshot del WebSocket, convertido a lo que espera la gráfica. Es el
// mismo objeto que usa el histórico, así que las dos vistas comparten todo el
// resto del código.
function muestraDeSnapshot(payload){
  var d = payload.data || {};
  function n(v){ var x = parseFloat(v); return isFinite(x) ? x : null; }
  var p = {
    n_vuelta: Math.round(n(d.n_lap) || 0),
    t_vuelta: n(d.t_vuelta) || 0,
    // d_vuelta viaja en km por todo el sistema; el eje de Ploteo está en metros
    d_vuelta: +(((n(d.d_vuelta) || 0) * 1000)).toFixed(1),
    lat: n(d.gps_lat), lon: n(d.gps_lon)
  };
  VARIABLES.forEach(function(v){ p[v.id] = n(d[v.id]); });
  return p;
}

function empujarVivo(payload){
  if (!vivo.corriendo) return;
  var p = muestraDeSnapshot(payload);
  // El cruce de meta reinicia t_vuelta. Sin vaciar el buffer, la ventana
  // deslizante compara el tiempo de la vuelta nueva con el de la vieja y borra
  // todo o no borra nada, según el caso.
  if (vivo.buffer.length && p.t_vuelta < vivo.buffer[vivo.buffer.length-1].t_vuelta) vivo.buffer = [];
  vivo.vuelta = p.n_vuelta;
  vivo.buffer.push(p);
  var limite = p.t_vuelta - VENTANA_S;
  while (vivo.buffer.length && vivo.buffer[0].t_vuelta < limite) vivo.buffer.shift();
  vivo.ultimo = Date.now();
  vivo.pintar = true;
  var hint = document.getElementById('v-hint');
  if (hint) hint.textContent = 'vuelta ' + p.n_vuelta + ' · ' + p.t_vuelta.toFixed(1) + ' s' +
    (vivo.zoom ? ' · vista fija, doble clic para soltar' : '');
}

function redibujarVivo(){
  var ejeX = document.getElementById('v-x').value;
  var ys = marcadasDe(document.getElementById('v-y'));
  var b = vivo.buffer;
  if (!b.length || !ys.length){ Plotly.react('g-vivo', [], JSON.parse(JSON.stringify(LAYOUT_BASE)), CONFIG_VIVO); return; }

  var dispersion = !esEjeDeRecorrido(ejeX);
  var trazas = ys.map(function(y,k){
    return {x:b.map(function(p){return sano(p, ejeX);}),
            y:b.map(function(p){ return sano(p, y); }),
            name:meta(y).nombre, type:'scattergl',
            mode: dispersion ? 'markers' : 'lines',
            marker:{size:4, color:COLORES[k], symbol:SIMBOLOS[k]},
            line:{width:1.7, color:COLORES[k]},
            yaxis: k===0 ? 'y' : 'y'+(k+1)};
  });

  var lay = JSON.parse(JSON.stringify(LAYOUT_BASE));
  lay.dragmode = 'pan';
  lay.xaxis = {title:{text:meta(ejeX).nombre+' ['+meta(ejeX).unidad+']',font:{size:9}},
               gridcolor:'#1a1a1a', zerolinecolor:'#222', fixedrange:false};
  if (ejeX === 't_vuelta'){
    // Ventana fija de 20 s. Anclada en cero durante los primeros 20 s de cada
    // vuelta: sin esa sujeción el eje arrancaba en −20 s, y un tiempo de vuelta
    // negativo no significa nada.
    var ult = b[b.length-1].t_vuelta;
    var ini = Math.max(0, ult - VENTANA_S);
    lay.xaxis.range = [ini, ini + VENTANA_S];
  } else if (esEjeDeRecorrido(ejeX)){
    // En distancia o posición, la ventana la marca lo que realmente hay en el
    // buffer: los mismos 20 s cubren más o menos metros según la velocidad,
    // así que un ancho fijo dejaría hueco vacío o recortaría datos
    var d0 = sano(b[0], ejeX), d1 = sano(b[b.length-1], ejeX);
    if (d0 !== null && d1 !== null) lay.xaxis.range = (d1 > d0) ? [d0, d1] : [d0, d0 + 10];
  }
  if (ys.length >= 3) lay.xaxis.domain = [0.085, 1];
  var rangos = cerosAlineados(b, ys);
  ys.forEach(function(y,k){
    var ex = extremosDe([b], y);
    lay[k===0 ? 'yaxis' : 'yaxis'+(k+1)] = ejeY(k, meta(y).nombre+' ['+meta(y).unidad+']', COLORES[k],
      y, false, rangos[k], ex && ex.min, ex && ex.max);
  });
  // La vista que puso el usuario manda sobre la ventana deslizante y sobre el
  // autoescalado, hasta que la suelte con doble clic
  if (vivo.zoom){
    Object.keys(vivo.zoom).forEach(function(k){
      if (!lay[k]) return;
      lay[k].range = vivo.zoom[k].slice();
      lay[k].autorange = false;
    });
  }
  Plotly.react('g-vivo', trazas, lay, CONFIG_VIVO);
}

// ═
//  HISTÓRICO
// ═
var mapa, capaTrazado = [], marcadorCursor = null, ultimoAjuste = '';
// Ancho del coche. La traza se dibuja con ese grosor REAL, no con un número de
// píxeles: así lo que se ve en el mapa es la huella que deja el coche, y dos
// vueltas se pisan cuando de verdad pasaron por el mismo asfalto, no porque la
// línea de dibujo sea más ancha que la separación entre ellas.
// Con una sola traza la línea va gruesa para que se lea. Con las cinco vueltas
// dibujadas a la vez tiene que ser fina, o cada una taparía a sus vecinas: van
// a poco más de un metro unas de otras y una línea de 4.5 m las cubre todas.
var ANCHO_UNA_M = 4.5, ANCHO_VARIAS_M = 1.2;
function grosorPx(anchoM){
  if (!mapa) return 3;
  var lat = mapa.getCenter().lat;
  var mPorPx = 156543.03392 * Math.cos(lat*Math.PI/180) / Math.pow(2, mapa.getZoom());
  return Math.max(0.8, (anchoM || ANCHO_UNA_M) / mPorPx);
}
// Orígenes ya evaluados contra la regla de medir, tal como se dibujaron
var ORIGENES = [];
// Puntos dibujados en el mapa, para saber cuál hay bajo el ratón
var PUNTOS_MAPA = [];
var tipMapa = null;


function inicializarHist(){
  var cont = document.getElementById('h-origenes');
  for (var i=0;i<MAX_ORIGENES;i++) cont.appendChild(filaOrigen(i));

  llenarSelect(document.getElementById('h-x'), EJES_X, 't_vuelta');
  construirLista(document.getElementById('h-y'), ['speed_v','p_hv'], function(){
    sincronizarSelectorMapa();
    redibujarHist();
  });
  document.getElementById('h-x').onchange = redibujarHist;
  document.getElementById('h-mapvar').onchange = dibujarMapa;
  document.getElementById('h-maporigen').onchange = function(){ ultimoAjuste=''; dibujarMapa(); };

  // renderer canvas: una sesión completa son ~2000 segmentos, y con el
  // renderizador SVG por defecto eso son 2000 nodos en el DOM
  // Zoom gradual: por defecto Leaflet salta de nivel entero en nivel entero
  // (cada paso duplica la escala). Con pasos de 0.1 y la rueda repartida en
  // mas desplazamiento, acercar se siente continuo.
  mapa = L.map('pl-mapa', {zoomControl:true, attributionControl:false, renderer:L.canvas(),
                           zoomSnap:0.1, zoomDelta:0.5, wheelPxPerZoomLevel:160, wheelDebounceTime:20});
  var pendiente = false;
  mapa.on('mousemove', function(ev){
    if (pendiente) return;
    pendiente = true;
    requestAnimationFrame(function(){ pendiente = false; puntoBajoRaton(ev.latlng); });
  });
  mapa.on('mouseout', function(){
    if (tipMapa){ mapa.removeLayer(tipMapa); tipMapa = null; }
    quitarLineaMapa();
  });
  // El grosor esta en metros reales, asi que al cambiar el zoom hay que
  // recalcular los pixeles. Sin esto la linea conservaba el grosor del zoom al
  // que se dibujo y dejaba de corresponder a metros.
  mapa.on('zoomend', function(){
    capaTrazado.forEach(function(c){
      var px = grosorPx(c.anchoM);
      c.setStyle(c.esPunto ? {radius: px/2} : {weight: px});
    });
  });
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{maxZoom:19}).addTo(mapa);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png',{maxZoom:19,opacity:0.65}).addTo(mapa);
  // Encuadre de arranque: en el demo era el centro de la pista simulada, que
  // aquí no existe. Da igual dónde empiece, porque el primer dibujo del mapa
  // ajusta el encuadre a las coordenadas reales de lo graficado.
  mapa.setView([19.5, -99.13], 15);

  Plotly.newPlot('g-hist', [], JSON.parse(JSON.stringify(LAYOUT_BASE)), CONFIG_HIST);
  document.getElementById('g-hist').on('plotly_hover', function(ev){
    // Se pasa el VALOR del eje X, no el índice: cada origen busca después su
    // propio punto más cercano a esa misma distancia o instante.
    // También el número de traza, para saber sobre qué origen está el cursor.
    moverCursor(ev.points[0].x, ev.points[0].curveNumber, ev.points[0].pointIndex);
  });

  // Las dos primeras filas arrancan en el día de hoy: es la tanda que se acaba
  // de correr, que es lo que uno quiere mirar al abrir la pestaña.
  var hoy = new Date().toISOString().slice(0,10);
  var filas = document.querySelectorAll('#h-origenes .pl-origen-row');
  for (var k=0;k<2 && k<filas.length;k++){
    var f = filas[k];
    f.querySelector('.pl-o-dia').value = hoy;
    llenarSesiones(f.querySelector('.pl-o-dia'), f.querySelector('.pl-o-sesion'),
                   f.querySelector('.pl-o-alcance'), null, k === 0 ? 'all' : '1');
  }

  sincronizarSelectorMapa();
  redibujarHist();
}


// ── Un origen = día → sesión → alcance (sesión completa o vuelta N) ──
// El día es un campo de fecha y no una lista: el sistema real acumula tandas
// indefinidamente y una lista de todos los días con datos sería otra consulta
// y un desplegable que crece para siempre.
function filaOrigen(i){
  var div = document.createElement('div');
  div.className = 'pl-origen-row';
  div.innerHTML = '<input type="color" class="pl-o-color" value="'+COLORES[i]+'" title="Color de esta fila">' +
                  '<input type="date" class="pl-o-dia">' +
                  '<select class="pl-o-sesion"><option value="">—</option></select>' +
                  '<select class="pl-o-alcance"><option value="">—</option></select><span></span>';

  var inpD = div.querySelector('.pl-o-dia'),
      selS = div.querySelector('.pl-o-sesion'),
      selA = div.querySelector('.pl-o-alcance');

  // La primera fila arranca en la sesión completa y la segunda en una vuelta
  // suelta: con las dos en "sesión completa" del mismo día, la pantalla abre
  // dibujando dos veces lo mismo y avisando de orígenes repetidos.
  var porDefecto = (i === 0) ? 'all' : '1';
  inpD.onchange = function(){ llenarSesiones(inpD, selS, selA, null, porDefecto); };
  selS.onchange = function(){ llenarAlcance(inpD, selS, selA, porDefecto); };
  selA.onchange = redibujarHist;
  div.querySelector('.pl-o-color').onchange = redibujarHist;
  return div;
}

function llenarSesiones(inpD, selS, selA, sesionPref, alcancePref){
  selS.innerHTML = '';
  selA.innerHTML = '';
  if (!inpD.value){ selS.disabled = selA.disabled = true; redibujarHist(); return; }
  selS.disabled = selA.disabled = false;
  opcion(selS, '', 'Cargando…');
  cargarSesionesDe(inpD.value).then(function(ses){
    selS.innerHTML = '';
    if (!ses.length){ opcion(selS, '', '— sin sesiones —'); redibujarHist(); return; }
    ses.forEach(function(s){ opcion(selS, String(s), 'Sesión ' + s); });
    if (sesionPref && ses.indexOf(sesionPref) >= 0) selS.value = sesionPref;
    llenarAlcance(inpD, selS, selA, alcancePref || 'all');
  });
}

// El alcance no se puede ofrecer sin saber qué vueltas tiene la sesión, y eso
// solo lo sabe el backend: aquí es donde se trae la serie entera.
function llenarAlcance(inpD, selS, selA, preferido){
  selA.innerHTML = '';
  if (!inpD.value || !selS.value){ redibujarHist(); return; }
  opcion(selA, '', 'Cargando…');
  estado('Cargando sesión ' + selS.value + ' del ' + inpD.value + '…');
  cargarSerie(inpD.value, selS.value).then(function(s){
    selA.innerHTML = '';
    if (!s.vueltas.length){
      opcion(selA, '', '— sin vueltas —');
      estado('La sesión ' + selS.value + ' no tiene vueltas cerradas.', 'aviso');
      redibujarHist(); return;
    }
    opcion(selA, 'all', 'Sesión completa');
    s.vueltas.forEach(function(v){ opcion(selA, String(v), 'Vuelta ' + v); });
    selA.value = preferido || 'all';
    estado(s.paso > 1
      ? 'Sesión ' + selS.value + ': ' + s.n + ' muestras, una de cada ' + s.paso + ' (serie larga).'
      : '');
    redibujarHist();
  }).catch(function(e){
    selA.innerHTML = '';
    opcion(selA, '', '— error —');
    estado('No se pudo leer la sesión: ' + e.message, 'error');
    redibujarHist();
  });
}

function origenesActivos(){
  var res = [];
  document.querySelectorAll('#h-origenes .pl-origen-row').forEach(function(row, i){
    var d = row.querySelector('.pl-o-dia').value,
        s = row.querySelector('.pl-o-sesion').value,
        a = row.querySelector('.pl-o-alcance').value;
    if (!d || !s || !a) return;
    var datos = (a === 'all') ? datosSesion(d, s) : datosVuelta(d, s, +a);
    if (!datos.length) return;   // aún cargando, o vuelta sin muestras
    res.push({idx:i, color:row.querySelector('.pl-o-color').value, fecha:d, sesion:s, alcance:a,
      etiqueta: d.slice(5) + ' S' + s + ' ' + (a === 'all' ? 'completa' : 'V' + a),
      datos: datos});
  });
  return res;
}

// El selector del mapa solo ofrece las variables ya elegidas en Y
// Con varios ejes Y superpuestos, cada uno se escala por su cuenta y el cero de
// cada variable cae a una altura distinta. Eso engaña: la corriente cruza su
// cero a media pantalla mientras el acelerador cruza el suyo abajo del todo, y
// parece que pasan cosas distintas en el mismo instante. Aquí se calcula un
// rango por eje tal que TODOS pongan su cero a la misma altura.
//
// La cuenta: si el cero tiene que quedar a la fracción R desde abajo, el rango
// de un eje es [-R·h, (1-R)·h], y basta con elegir h lo bastante grande para
// que quepan los datos. Se toma la R más exigente de todas las variables.
function cerosAlineados(datos, campos){
  var lim = campos.map(function(c){
    var mn = Infinity, mx = -Infinity;
    for (var i=0;i<datos.length;i++){
      var v = sano(datos[i], c);
      if (v === null) continue;
      if (v < mn) mn = v;
      if (v > mx) mx = v;
    }
    if (mn === Infinity) return null;
    var margen = (mx - mn) * 0.06 || 1;
    return {lo: Math.min(mn - margen, 0), hi: Math.max(mx + margen, 0)};
  });

  var R = 0;
  lim.forEach(function(l){
    if (!l) return;
    var h = l.hi - l.lo;
    if (h > 0) R = Math.max(R, -l.lo / h);
  });

  // Una variable que nunca cruza el cero manda al resto contra la pared. La
  // corriente del pack, por ejemplo, es negativa toda la vuelta: para poner su
  // cero a la vista habría que dejar casi toda la altura vacía en los demás
  // ejes. Pasado ese punto no compensa, y se prefiere no alinear a alinear
  // dejando las señales aplastadas en una franja.
  if (R > 0.6) return campos.map(function(){ return null; });

  return lim.map(function(l){
    if (!l) return null;
    var h;
    if (R === 0){
      h = Math.max(l.hi, 1e-9);
    } else {
      h = 0;
      if (l.hi > 0) h = Math.max(h, l.hi/(1-R));
      if (l.lo < 0) h = Math.max(h, -l.lo/R);
    }
    if (!isFinite(h) || h <= 0) return null;
    return [-R*h, (1-R)*h];
  });
}

// Mínimo y máximo de una variable sobre todos los orígenes que comparten su eje
function extremosDe(origenes, campo){
  var mn = Infinity, mx = -Infinity;
  origenes.forEach(function(o){
    var datos = o.datos || o;
    for (var i=0;i<datos.length;i++){
      var v = sano(datos[i], campo);
      if (v === null) continue;
      if (v < mn) mn = v;
      if (v > mx) mx = v;
    }
  });
  return (mn === Infinity) ? null : {min:mn, max:mx};
}

function sincronizarSelectorMapa(){
  var sel = document.getElementById('h-mapvar');
  var ys = marcadasDe(document.getElementById('h-y'));
  var previo = sel.value;
  sel.innerHTML = '';
  if (!ys.length){ opcion(sel, '', '— elige variables —'); return; }
  ys.forEach(function(id){ var m = meta(id); opcion(sel, id, m.nombre+' ['+m.unidad+']'); });
  sel.value = (ys.indexOf(previo) >= 0) ? previo : ys[0];
}

// El selector de origen del mapa solo ofrece los orígenes ya graficados
function sincronizarOrigenMapa(){
  var sel = document.getElementById('h-maporigen');
  var orig = origenesActivos();
  var previo = sel.value;
  sel.innerHTML = '';
  if (!orig.length){ opcion(sel, '', '— sin orígenes —'); return; }
  orig.forEach(function(o){ opcion(sel, String(o.idx), o.etiqueta); });
  var existe = orig.some(function(o){ return String(o.idx) === previo; });
  sel.value = existe ? previo : String(orig[0].idx);
}

function redibujarHist(){
  var selX = document.getElementById('h-x');
  var ys = marcadasDe(document.getElementById('h-y'));
  var orig = origenesActivos();

  // El cursor reutiliza estos orígenes tal como se dibujaron
  ORIGENES = orig;

  var ejeX = selX.value;
  var dispersion = !esEjeDeRecorrido(ejeX);

  // Cada señal en su propia franja, apiladas y compartiendo el eje X. Antes iban
  // superpuestas en tres ejes Y sobre el mismo dibujo, y con tres variables la
  // maraña no dejaba leer ninguna. Separadas, cada una tiene toda su altura.
  //
  // Con una franja por variable, el color puede identificar al ORIGEN y ya no
  // hacen falta trazos punteados para distinguir variables: dentro de una franja
  // solo hay una variable, y lo que se compara son las vueltas.
  var trazas = [];
  orig.forEach(function(o, io_){
    ys.forEach(function(y,k){
      trazas.push({
        x:o.datos.map(function(p){ return sano(p, ejeX); }),
        y:o.datos.map(function(p){ return sano(p, y); }),
        name:o.etiqueta, type:'scattergl',
        mode: dispersion ? 'markers' : 'lines',
        marker:{size:3, color:o.color, opacity:0.9},
        line:{width:1.8, color:o.color},
        yaxis: ejeDeFranja(k),
        legendgroup: o.etiqueta,
        // Una entrada de leyenda por origen, no una por origen y variable: con
        // tres de cada saldrian nueve para tres colores
        showlegend: k === 0
      });
    });
  });

  var lay = JSON.parse(JSON.stringify(LAYOUT_BASE));
  lay.xaxis = {title:{text:meta(ejeX).nombre+' ['+meta(ejeX).unidad+']',font:{size:9}},
               gridcolor:'#1a1a1a', zerolinecolor:'#222', fixedrange:false,
               hoverformat: '.'+(meta(ejeX).dec !== undefined ? meta(ejeX).dec : 2)+'f'};
  lay.hovermode = dispersion ? 'closest' : 'x unified';
  // Arrastrar DESPLAZA la vista, no recorta. El rectángulo de selección de
  // Plotly reencuadra los dos ejes a la vez y deja la escala del eje X en
  // valores arbitrarios; con desplazamiento + rueda el zoom es el de siempre.
  lay.dragmode = 'pan';
  // Al cambiar de variables o de orígenes se vuelve a la vista completa, que es
  // lo correcto: el zoom anterior estaba puesto sobre otros datos. Pero mover el
  // cursor NO redibuja, así que la ampliación aguanta mientras se lee la tabla.
  lay.annotations = [];
  ys.forEach(function(y,k){
    var ex = extremosDe(orig, y);
    var e = ejeY(k, '', '#b0b0b0', y, false, null, ex && ex.min, ex && ex.max);
    e.domain = dominioFranja(k, ys.length);
    e.anchor = 'x';
    delete e.overlaying; delete e.side; delete e.position;
    lay[ejeDeFranja(k).replace('y', 'yaxis').replace('yaxis', 'yaxis')] = e;
    // El nombre va pegado a su franja: yref al dominio del eje, así que sube y
    // baja con ella y se queda donde esté la señal aunque se desplace la vista
    lay.annotations.push({
      text: meta(y).nombre + '  [' + meta(y).unidad + ']',
      xref:'paper', x:0.004, xanchor:'left',
      yref: ejeDeFranja(k) + ' domain', y:1, yanchor:'top',
      showarrow:false, font:{size:10, color:'#d8d8d8'},
      bgcolor:'rgba(13,13,13,0.75)', borderpad:3
    });
  });
  // La leyenda va pegada encima de la primera franja, no flotando a distancia:
  // con y:1.13 dejaba una banda vacía de casi cien píxeles sobre la gráfica.
  lay.legend = {orientation:'h', x:0, y:1, xanchor:'left', yanchor:'bottom', font:{size:9}};
  lay.margin = {l:56, r:16, t:24, b:42};
  // El eje X, con sus números y su título, abajo del todo: anclado a la franja
  // de arriba quedaba metido entre la primera y la segunda
  lay.xaxis.anchor = ejeDeFranja(ys.length - 1);
  Plotly.react('g-hist', trazas, lay, CONFIG_HIST);

  avisarComparacionDudosa(orig, ejeX);

  // La tabla del cursor corresponde a la selección anterior: si no se limpia,
  // sigue mostrando variables ya desmarcadas o columnas de orígenes quitados
  limpiarCursor();

  sincronizarOrigenMapa();
  dibujarMapa();
}

// Una herramienta de análisis no debe dejar comparar en silencio cosas que no
// son equivalentes.
function avisarComparacionDudosa(orig, ejeX){
  var cont = document.getElementById('h-aviso');
  var avisos = [];

  // Comparar dos vueltas por odómetro es el error clásico: se ve una gráfica
  // perfectamente razonable en la que, a mitad de vuelta, cada traza está en
  // un punto distinto del circuito.
  if (orig.length > 1 && ejeX === 'd_vuelta'){
    avisos.push('<b>Cuidado al comparar.</b> La distancia recorrida es la ' +
                'trayectoria de cada vuelta: abrirse en una curva suma metros que se ' +
                'arrastran hasta la meta, así que el mismo valor de X cae en puntos ' +
                'cada vez más separados del circuito. Al principio de la vuelta las trazas ' +
                'van alineadas; hacia el final pueden quedar a decenas de metros unas de ' +
                'otras. El mapa dice dónde estaba cada una de verdad.');
  }

  // En una sesion el eje se encadena vuelta tras vuelta, asi que una vuelta
  // suelta solo coincide con la PRIMERA vuelta de la sesion y a partir de ahi
  // se queda sin datos, aunque la grafica siga dibujando la sesion.
  if (orig.length > 1 && esEjeDeRecorrido(ejeX)){
    var completas = orig.filter(function(o){ return o.alcance === 'all'; }).length;
    if (completas > 0 && completas < orig.length){
      avisos.push('<b>Alcances mezclados.</b> Se están comparando vueltas sueltas con sesiones completas: ' +
                  'en una vuelta el eje cuenta desde su cruce de meta, y en una sesión se acumula sobre todas las vueltas. ' +
                  'La vuelta suelta solo coincide con la primera vuelta de la sesión; más allá, la tabla marca «sin dato».');
    }
  }

  var vistos = {}, duplicados = [];
  orig.forEach(function(o){
    var k = o.fecha+'|'+o.sesion+'|'+o.alcance;
    if (vistos[k]) duplicados.push(o.etiqueta); else vistos[k] = true;
  });
  if (duplicados.length){
    avisos.push('<b>Orígenes repetidos.</b> ' + duplicados[0] + ' está seleccionado más de una vez; ' +
                'las trazas se dibujan encimadas y la tabla muestra columnas idénticas.');
  }

  cont.innerHTML = avisos.map(function(a){ return '<div class="aviso-comparacion">'+a+'</div>'; }).join('');
}

function puntoBajoRaton(latlng){
  if (!PUNTOS_MAPA.length) return;
  // Tolerancia en píxeles de pantalla, convertida a metros al zoom actual
  var mPorPx = 156543.03392 * Math.cos(latlng.lat*Math.PI/180) / Math.pow(2, mapa.getZoom());
  var tolM = 12 * mPorPx, ml = mLon(latlng.lat), mejor = null, dMin = Infinity;
  for (var k=0; k<PUNTOS_MAPA.length; k++){
    var p = PUNTOS_MAPA[k];
    var dx = (p.lon - latlng.lng)*ml, dy = (p.lat - latlng.lat)*M_LAT, d2 = dx*dx + dy*dy;
    if (d2 < dMin){ dMin = d2; mejor = p; }
  }
  if (!mejor || Math.sqrt(dMin) > tolM){
    if (tipMapa){ mapa.removeLayer(tipMapa); tipMapa = null; }
    quitarLineaMapa();
    return;
  }

  var o = mejor.o, i = mejor.i, d = o.datos[i];
  var campo = document.getElementById('h-mapvar').value, m = meta(campo);
  var v = sano(d, campo);
  var html = '<b>' + o.etiqueta + '</b>' + (d.n_vuelta !== undefined ? ' · vuelta ' + d.n_vuelta : '') +
    '<br>' + m.nombre + ': <b>' + (v !== null ? formatear(v, campo) + ' ' + m.unidad : 'sin dato') + '</b>' +
    '<br>tiempo ' + d.t_vuelta.toFixed(1) + ' s · recorridos ' + d.d_vuelta.toFixed(0) + ' m';
  // La posición tiene que estar puesta antes de añadirlo al mapa, o Leaflet falla
  if (!tipMapa){
    tipMapa = L.tooltip({direction:'top', offset:[0,-8], opacity:0.95})
      .setLatLng([d.lat, d.lon]).setContent(html).addTo(mapa);
  } else {
    tipMapa.setLatLng([d.lat, d.lon]).setContent(html);
  }

  // Sincroniza la gráfica y la tabla con ese mismo punto
  var ejeX = document.getElementById('h-x').value;
  var x = sano(d, ejeX);
  if (x === null || x === undefined) return;
  var ys = marcadasDe(document.getElementById('h-y'));
  var k2 = ORIGENES.indexOf(o);
  if (k2 < 0 || !ys.length) return;
  moverCursor(x, k2*ys.length, i);
  // Línea vertical en la gráfica en ese mismo punto. Plotly no dibuja su propia
  // línea de cursor en las gráficas WebGL cuando el ratón no está encima, así
  // que se pone como una forma de la gráfica.
  Plotly.relayout('g-hist', {shapes:[{type:'line', xref:'x', yref:'paper', x0:x, x1:x, y0:0, y1:1,
                                       line:{color:'#d8d8d8', width:1, dash:'dot'}}]});
}
function quitarLineaMapa(){
  var g = document.getElementById('g-hist');
  if (g && g.layout && g.layout.shapes && g.layout.shapes.length) Plotly.relayout('g-hist', {shapes:[]});
}

function limpiarCursor(){
  document.getElementById('h-valores').innerHTML =
    '<div class="sin-cursor">Pasa el cursor sobre la gráfica.</div>';
  document.getElementById('h-cursor-pos').textContent = '';
  if (marcadorCursor){ mapa.removeLayer(marcadorCursor); marcadorCursor = null; }
}

// ── Mapa: el origen elegido, coloreado por la variable elegida ──
function dibujarMapa(){
  capaTrazado.forEach(function(c){ mapa.removeLayer(c); });
  PUNTOS_MAPA = [];
  capaTrazado = [];

  // Los orígenes ya evaluados contra la regla de medir: son los únicos que
  // llevan la posición en la pista, y sin ella no se puede agrupar por metro
  var orig = ORIGENES;
  var idxSel = document.getElementById('h-maporigen').value;
  var o = orig.find(function(x){ return String(x.idx) === idxSel; }) || orig[0];
  var campo = document.getElementById('h-mapvar').value;
  var barra = document.getElementById('barra-color');

  if (!o || !campo){
    document.getElementById('h-mapname').textContent = '—';
    document.getElementById('h-min').textContent = '—';
    document.getElementById('h-max').textContent = '—';
    document.getElementById('h-cursor-pos').textContent = '';
    barra.style.background = '#222';
    // Sin origen no hay trazado: el marcador del cursor tampoco debe quedarse
    if (marcadorCursor){ mapa.removeLayer(marcadorCursor); marcadorCursor = null; }
    return;
  }

  var m = meta(campo);
  var serieMapa = serieDe(o.fecha, o.sesion);
  var nVueltas = (o.alcance === 'all' && serieMapa) ? serieMapa.vueltas.length : 1;

  // La escala se calcula sobre TODOS los orígenes activos, no solo el que se
  // muestra. Si cada uno se normalizara consigo mismo, el mismo color
  // significaría valores distintos y alternar entre orígenes en el mapa daría
  // una comparación visual falsa.
  // La escala se recorta al percentil 2–98. Con los extremos crudos, un solo
  // pico —una punta de corriente, un salto de GPS— comprimía todo lo demás:
  // con un valor aislado de 45 kW, el 100 % de las muestras caía en el primer
  // tercio de color y el mapa dejaba de distinguir nada.
  var todos = [];
  orig.forEach(function(x){
    x.datos.forEach(function(p){
      var v = sano(p, campo);
      if (v !== null) todos.push(v);
    });
  });
  // Del mínimo registrado al máximo registrado, sin recortar: es lo que pidió el
  // equipo. Que se distingan los tonos lo resuelve la escala de seis colores.
  var min = Infinity, max = -Infinity, recortada = false;
  todos.forEach(function(v){ if (v < min) min = v; if (v > max) max = v; });
  if (min === Infinity){                     // la variable no tiene ni un dato
    document.getElementById('h-mapname').textContent = o.etiqueta + ' · ' + m.nombre + '  (sin datos)';
    document.getElementById('h-min').textContent = '—';
    document.getElementById('h-max').textContent = '—';
    barra.style.background = '#222';
    return;
  }
  var comun = orig.length > 1;
  document.getElementById('h-min').textContent = formatear(min, campo)+' '+m.unidad;
  document.getElementById('h-max').textContent = formatear(max, campo)+' '+m.unidad +
    (comun ? '  (escala común)' : '') + (recortada ? '  · p2–p98' : '');

  var paradas = [];
  for (var f=0; f<=20; f++) paradas.push(escalaColor(f/20)+' '+(f*5)+'%');
  barra.style.background = 'linear-gradient(to right,'+paradas.join(',')+')';

  var huecosGps = 0, huecosValor = 0;
  var esSesion = (o.alcance === 'all');
  var ancho = esSesion ? ANCHO_VARIAS_M : ANCHO_UNA_M;

  // Se dibujan las COORDENADAS reales de cada vuelta, coloreadas con el valor de
  // esa vuelta en ese punto: se ve por donde fue el coche de verdad, salidas de
  // pista y entradas a boxes incluidas. Promediar las vueltas se probo y se
  // descarto, porque esconde justo las diferencias que se buscan.
  for (var i=1;i<o.datos.length;i++){
    var a = o.datos[i-1], b = o.datos[i];
    // Un corte de GPS lanzaba una excepción dentro de Leaflet y dejaba el mapa
    // a medio dibujar: ahora el tramo simplemente no se traza
    if (!coordValida(a) || !coordValida(b)){ huecosGps++; continue; }
    // El salto de meta a meta entre dos vueltas no es un tramo recorrido
    if (a.n_vuelta !== undefined && b.n_vuelta !== undefined && a.n_vuelta !== b.n_vuelta) continue;
    var vb = sano(b, campo);
    if (vb === null){ huecosValor++; continue; }

    var f2 = max>min ? (vb-min)/(max-min) : 0.5;
    var color = escalaColor(f2);
    var px = grosorPx(ancho);
    // En una sesión se dibuja CADA punto de GPS, no una línea que los una. Con
    // cinco vueltas a menos de dos metros unas de otras, una línea continua las
    // funde en un solo trazo y no se distingue cuál es cuál; los puntos sueltos
    // dejan ver la nube, como las marcas de neumático sobre el asfalto.
    // Trayectorias: cada vuelta es un trazo continuo. Con las cinco a la vez la
    // línea va fina —1.2 m, menos que los 1.8 m que las separan— para que no se
    // tapen entre ellas.
    var capa = L.polyline([[a.lat,a.lon],[b.lat,b.lon]],
      {color: color, weight: px, opacity: 0.95}).addTo(mapa);
    capa.anchoM = ancho;
    capaTrazado.push(capa);
    PUNTOS_MAPA.push({lat:b.lat, lon:b.lon, o:o, i:i});
  }

  var faltantes = [];
  if (huecosGps) faltantes.push(huecosGps+' sin GPS');
  if (huecosValor) faltantes.push(huecosValor+' sin valor');
  document.getElementById('h-mapname').textContent =
    o.etiqueta + ' · ' + m.nombre +
    (esSesion ? '  (' + nVueltas + ' trayectorias, cada una con sus valores)' : '') +
    (faltantes.length ? '  · '+faltantes.join(', ') : '');

  var clave = o.fecha+'|'+o.sesion+'|'+o.alcance;
  if (clave !== ultimoAjuste){
    // animate:false — con la animación por defecto el encuadre puede quedarse
    // a medias y el mapa se queda en el zoom anterior
    var puntosValidos = o.datos.filter(coordValida).map(function(p){return [p.lat,p.lon];});
    if (puntosValidos.length) mapa.fitBounds(L.latLngBounds(puntosValidos), {padding:[18,18], animate:false});
    ultimoAjuste = clave;
  }
}

// ── Cursor: marcador en el mapa + valores de TODOS los orígenes ──
// Recibe el VALOR del eje X. Cada origen localiza su punto más cercano a ese
// valor, de modo que la comparación es siempre en la misma distancia (o el
// mismo instante), no en la misma posición del arreglo.
function moverCursor(valorX, nTraza, idxPunto){
  var orig = ORIGENES;
  var ys = marcadasDe(document.getElementById('h-y'));
  var cont = document.getElementById('h-valores');
  if (!orig.length || !ys.length){
    cont.innerHTML = '<div class="sin-cursor">Elige orígenes y variables.</div>';
    return;
  }

  var ejeX = document.getElementById('h-x').value;
  var dispersion = !esEjeDeRecorrido(ejeX);

  if (dispersion){
    // Nube de puntos: el eje X es una variable cualquiera, no una posición en
    // la vuelta. Buscar "el mismo X" en los demás orígenes daría puntos de
    // lugares opuestos del circuito que solo coinciden en ese valor, así que
    // se muestra únicamente el origen sobre el que está el cursor.
    var oCursor = orig[Math.floor((nTraza||0) / ys.length)] || orig[0];
    orig.forEach(function(o){
      o.punto = (o === oCursor) ? o.datos[idxPunto] : null;
      o.iPunto = (o === oCursor) ? idxPunto : null;
    });
  } else {
    // Series contra tiempo o distancia: cada origen busca su punto más cercano
    // al mismo valor de X, para que la comparación sea del mismo punto de pista
    orig.forEach(function(o){
      var i = indiceMasCercano(o.datos, ejeX, valorX);
      o.punto = (i === null) ? null : o.datos[i];
      o.iPunto = i;
    });
  }

  // El marcador se coloca sobre el origen que se está mostrando en el mapa
  var idxSel = document.getElementById('h-maporigen').value;
  var oMapa = orig.find(function(x){ return String(x.idx) === idxSel; }) || orig[0];
  // En dispersión solo un origen tiene punto; si no es el del mapa, se marca ese
  if (!oMapa.punto){ oMapa = orig.find(function(x){ return !!x.punto; }) || oMapa; }

  if (oMapa.punto && coordValida(oMapa.punto)){
    if (marcadorCursor) mapa.removeLayer(marcadorCursor);
    marcadorCursor = L.circleMarker([oMapa.punto.lat, oMapa.punto.lon],
      {radius:7, color:'#fff', weight:2, fillColor:oMapa.color, fillOpacity:1}).addTo(mapa);
    document.getElementById('h-cursor-pos').textContent =
      'recorridos '+oMapa.punto.d_vuelta.toFixed(0)+' m · '+
      oMapa.punto.t_vuelta.toFixed(1)+' s';
  }

  var campoMapa = document.getElementById('h-mapvar').value;
  var html = '<table class="cursor-tabla"><thead><tr><th></th>';
  orig.forEach(function(o){ html += '<th style="color:'+o.color+'">'+o.etiqueta+'</th>'; });
  html += '</tr></thead><tbody>';

  // Un campo condicional que no se cumplió llega nulo. Escribirlo tal cual
  // pondría la palabra "null" donde debería verse que no hay dato.
  function celda(o, campo){
    if (!o.punto) return '<td>—</td>';
    var v = sano(o.punto, campo);
    return '<td>' + (v !== null ? formatear(v, campo) : '<span style="color:#555">sin dato</span>') + '</td>';
  }

  ['t_vuelta','d_vuelta'].forEach(function(campo){
    var m = meta(campo);
    html += '<tr><td>'+m.nombre+' ['+m.unidad+']</td>';
    orig.forEach(function(o){ html += celda(o, campo); });
    html += '</tr>';
  });
  ys.forEach(function(y){
    var m = meta(y), clase = (y === campoMapa) ? ' class="destacada"' : '';
    html += '<tr'+clase+'><td>'+m.nombre+' ['+m.unidad+']</td>';
    orig.forEach(function(o){ html += celda(o, y); });
    html += '</tr>';
  });
  html += '</tbody></table>';
  cont.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════════════════

// ── Sub-pestañas de Ploteo ──
function panelActivo(){
  var v = document.getElementById('panel-vivo');
  return (v && v.classList.contains('pl-on')) ? 'vivo' : 'hist';
}

var iniciado = false;
function arrancar(){
  if (iniciado) return;
  iniciado = true;
  inicializarVivo();
  inicializarHist();
}

document.addEventListener('DOMContentLoaded', function(){
  document.querySelectorAll('#tab-2 .pl-tab').forEach(function(t){
    t.onclick = function(){
      document.querySelectorAll('#tab-2 .pl-tab').forEach(function(x){ x.classList.remove('pl-on'); });
      document.querySelectorAll('#tab-2 .pl-panel').forEach(function(x){ x.classList.remove('pl-on'); });
      t.classList.add('pl-on');
      document.getElementById('panel-' + t.dataset.panel).classList.add('pl-on');
      // Plotly y Leaflet miden el contenedor al dibujar, y en una pestaña oculta
      // ese contenedor mide cero: hay que avisarles cuando se hace visible.
      ajustarTamanos();
    };
  });
});

function ajustarTamanos(){
  if (!iniciado) return;
  setTimeout(function(){
    try { Plotly.Plots.resize('g-vivo'); } catch (e) {}
    try { Plotly.Plots.resize('g-hist'); } catch (e) {}
    if (mapa && panelActivo() === 'hist'){
      mapa.invalidateSize(); ultimoAjuste = ''; dibujarMapa();
    }
  }, 60);
}

var temporizadorResize = null;
window.addEventListener('resize', function(){
  clearTimeout(temporizadorResize);
  temporizadorResize = setTimeout(ajustarTamanos, 150);
});

// La pestaña se construye la primera vez que se entra en ella, no al cargar la
// página: Plotly y Leaflet sobre contenedores ocultos dan tamaños de cero, y
// además el dashboard arranca sin pagar el coste de una pantalla que quizá no
// se abra.
window.PloteoTab = {
  abrir: function(){ arrancar(); ajustarTamanos(); }
};
// dashboard-render.js llama a esto en cada snapshot del WebSocket.
window.PloteoVivo = {
  push: function(payload){ if (iniciado) empujarVivo(payload); }
};

})();
