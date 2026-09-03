"""
test_automatizado.py — Pruebas automatizadas del Backend (pytest).

Cubre las funciones puras de backend_core/ que NO necesitan MQTT ni
InfluxDB reales: fisica.py, vueltas.py, y la validación de entrada de
meta_server.py. No prueba mqtt_listener.py/main() completo ni historicos.py
(requieren un broker MQTT / InfluxDB real corriendo) — esas partes se
siguen verificando a mano.

Cómo correrlas:
    cd software/Backend
    pip install pytest
    pytest -v

Ver la sección "Pruebas automatizadas" en README.md para más contexto.
"""

import pytest

from datetime import datetime, timedelta, timezone

from backend_core import config, fisica, meta_server, vueltas
from backend_core.estado import estado


@pytest.fixture(autouse=True)
def estado_limpio():
    """Reinicia el estado global antes de cada prueba — si no, una prueba
    podría "heredar" datos de la anterior (por ejemplo n_lap ya en 3)."""
    estado.__init__()
    yield


# ─── fisica.py ──────────────────────────────────────────────────────────────

class TestOcvToSocAux:
    def test_voltaje_bajo_la_tabla_da_cero(self):
        assert fisica.ocv_to_soc_aux(10.0) == 0.0

    def test_voltaje_sobre_la_tabla_da_cien(self):
        assert fisica.ocv_to_soc_aux(15.0) == 100.0

    def test_interpola_entre_dos_puntos_de_la_tabla(self):
        # Tabla tiene (12.0, 5.0) y (12.8, 10.0) — punto medio de voltaje
        # debe dar aprox punto medio de SOC.
        soc = fisica.ocv_to_soc_aux(12.4)
        assert 5.0 < soc < 10.0


class TestComputeDerived:
    def test_corriente_de_consumo_calcula_p_hv(self):
        data = {"curr_rms": 80.0, "rpm": 3000.0, "volt_p": 56.8, "acc_x": 0, "acc_y": 0, "acc_z": 1}
        derived = fisica.compute_derived(data, soc=85.0, curr_p=-60.0)
        assert derived["p_hv"] is not None
        assert derived["p_hv"] == pytest.approx(56.8 * 60.0, rel=0.01)

    def test_corriente_de_regen_calcula_p_regen_no_p_hv(self):
        data = {"curr_rms": 20.0, "rpm": 1000.0, "volt_p": 56.8, "acc_x": 0, "acc_y": 0, "acc_z": 1}
        derived = fisica.compute_derived(data, soc=85.0, curr_p=25.0)
        assert derived["p_hv"] is None
        assert derived["p_regen"] is not None

    def test_corriente_pequena_no_calcula_potencias(self):
        # abs(curr_p) < I_MIN (10.0) → ni consumo ni regen
        data = {"curr_rms": 5.0, "rpm": 500.0, "volt_p": 56.8, "acc_x": 0, "acc_y": 0, "acc_z": 1}
        derived = fisica.compute_derived(data, soc=85.0, curr_p=2.0)
        assert derived["p_hv"] is None
        assert derived["p_regen"] is None

    def test_eta_solo_se_calcula_con_p_hv_significativo(self):
        # p_hv <= 300W → eta debe quedar None aunque haya consumo
        data = {"curr_rms": 1.0, "rpm": 100.0, "volt_p": 12.0, "acc_x": 0, "acc_y": 0, "acc_z": 1}
        derived = fisica.compute_derived(data, soc=85.0, curr_p=-11.0)
        assert derived["eta"] is None


# ─── vueltas.py ─────────────────────────────────────────────────────────────

def _setear_meta_de_prueba():
    """Línea de meta corta orientada N-S; para cruzarla hay que variar
    longitud (E-O), no latitud."""
    vueltas.set_meta(20.0000, -103.0000, 20.0001, -103.0000)


class TestProcessLap:
    def test_primer_cruce_arma_pero_no_cuenta_vuelta(self):
        _setear_meta_de_prueba()
        vueltas.process_lap(20.00005, -103.00010, 40.0, 0.0, True)
        resultado = vueltas.process_lap(20.00005, -103.00000 + 0.00002, 40.0, 1.0, True)

        assert resultado["armado"] is True
        assert resultado["n_lap"] == 0

    def test_segundo_cruce_cierra_la_vuelta(self):
        _setear_meta_de_prueba()
        vueltas.process_lap(20.00005, -103.00010, 40.0, 0.0, True)
        vueltas.process_lap(20.00005, -103.00000 + 0.00002, 40.0, 1.0, True)

        vueltas.process_lap(20.00005, -103.00000 + 0.00002, 40.0, 21.0, True)
        resultado = vueltas.process_lap(20.00005, -103.00010, 40.0, 22.0, True)

        assert resultado["n_lap"] == 1
        assert len(resultado["laps"]) == 1
        assert resultado["laps"][0]["t_vuelta"] > 15  # LAP_T_MIN

    def test_vuelta_muy_corta_se_rechaza(self):
        # Cruce a menos de LAP_T_MIN (15s) del anterior no debe contar.
        _setear_meta_de_prueba()
        vueltas.process_lap(20.00005, -103.00010, 40.0, 0.0, True)
        vueltas.process_lap(20.00005, -103.00000 + 0.00002, 40.0, 1.0, True)  # arma

        vueltas.process_lap(20.00005, -103.00000 + 0.00002, 40.0, 3.0, True)
        resultado = vueltas.process_lap(20.00005, -103.00010, 40.0, 4.0, True)  # solo 3s después

        assert resultado["n_lap"] == 0

    def test_sin_sesion_activa_no_procesa(self):
        _setear_meta_de_prueba()
        resultado = vueltas.process_lap(20.00005, -103.00005, 40.0, 0.0, False)
        assert resultado["n_lap"] == 0
        assert resultado["armado"] is False

    def test_gps_sin_fix_se_ignora(self):
        _setear_meta_de_prueba()
        resultado = vueltas.process_lap(0.0, 0.0, 40.0, 0.0, True)
        assert resultado["d_vuelta"] == 0.0


class TestComputeLapEstimates:
    def test_sin_vueltas_completas_da_none(self):
        estimacion = vueltas.compute_lap_estimates([], E_HV_rest=1000.0)
        assert estimacion["d_rest"] is None
        assert estimacion["n_opt"] is None

    def test_con_dos_vueltas_calcula_vuelta_optima(self):
        laps = [
            {"n_lap": 1, "t_vuelta": 80.0, "d_vuelta": 1.0, "E_vuelta": 100.0},
            {"n_lap": 2, "t_vuelta": 75.0, "d_vuelta": 1.0, "E_vuelta": 90.0},
        ]
        estimacion = vueltas.compute_lap_estimates(laps, E_HV_rest=500.0)
        assert estimacion["n_opt"] in (1, 2)
        assert estimacion["d_rest"] is not None


# ─── estado.py ──────────────────────────────────────────────────────────────

def test_reset_lap_accumulators_deja_todo_en_cero():
    estado.lap_spd_max = 55.0
    estado.lap_spd_n = 10
    estado.reset_lap_accumulators()
    assert estado.lap_spd_max == 0.0
    assert estado.lap_spd_n == 0


# ─── meta_server.py — validación de entrada ─────────────────────────────────

class TestValidacionMetaServer:
    def test_fecha_valida_pasa_regex(self):
        assert meta_server._DATE_RE.match("2026-07-12")

    def test_fecha_malformada_no_pasa_regex(self):
        assert not meta_server._DATE_RE.match("12-07-2026")
        assert not meta_server._DATE_RE.match("2026/07/12")

    def test_session_id_valido_pasa_regex(self):
        assert meta_server._SESSION_ID_RE.match("2026-07-12_1")

    def test_intento_de_inyeccion_no_pasa_regex(self):
        assert not meta_server._SESSION_ID_RE.match('1" or true or "')
        assert not meta_server._SESSION_ID_RE.match("1; DROP TABLE x")


# ─── meta_server.py — CORS ──────────────────────────────────────────────────

class TestCorsMetaServer:
    """El header Access-Control-Allow-Origin estaba fijo en "*": cualquier
    página web podía leer estas respuestas desde el navegador de quien la
    visitara. Ahora respeta FENIX_ALLOWED_ORIGINS."""

    class _Peticion:
        """Lo mínimo que _cors_origin necesita de BaseHTTPRequestHandler."""
        def __init__(self, origin=None):
            self.headers = {"Origin": origin} if origin else {}
        _cors_origin = meta_server._MetaHandler._cors_origin

    def test_sin_lista_blanca_permite_cualquier_origen(self, monkeypatch):
        monkeypatch.setattr(config, "ALLOWED_ORIGINS", ["*"])
        assert self._Peticion("http://cualquiera.com")._cors_origin() == "*"

    def test_origen_en_la_lista_se_devuelve_tal_cual(self, monkeypatch):
        monkeypatch.setattr(config, "ALLOWED_ORIGINS", ["http://23.94.237.163:8080"])
        peticion = self._Peticion("http://23.94.237.163:8080")
        assert peticion._cors_origin() == "http://23.94.237.163:8080"

    def test_origen_ajeno_no_recibe_cabecera(self, monkeypatch):
        monkeypatch.setattr(config, "ALLOWED_ORIGINS", ["http://23.94.237.163:8080"])
        assert self._Peticion("http://sitio-ajeno.com")._cors_origin() is None

    def test_peticion_sin_origen_no_recibe_cabecera(self, monkeypatch):
        monkeypatch.setattr(config, "ALLOWED_ORIGINS", ["http://23.94.237.163:8080"])
        assert self._Peticion()._cors_origin() is None


# ─── config.py — coherencia de la zona horaria ──────────────────────────────

class TestDesfaseHorario:
    """El desfase de México se aplica en dos puntos opuestos del flujo:
    mqtt_listener lo RESTA al guardar (hora local del ESP32 → UTC) e
    historicos lo SUMA al consultar (fecha local → ventana UTC). Ambos leen
    config.TZ_OFFSET_HOURS; si alguien desalineara los signos, las sesiones
    guardadas dejarían de encontrarse sin que saltara ningún error."""

    def _guardar(self, texto_del_esp32):
        """Reproduce la conversión de mqtt_listener.py al escribir en InfluxDB."""
        return datetime.strptime(texto_del_esp32, "%Y-%m-%d %H:%M:%S.%f").replace(
            tzinfo=timezone(timedelta(hours=-config.TZ_OFFSET_HOURS))
        ).astimezone(timezone.utc).replace(tzinfo=None)

    def _ventana(self, fecha):
        """Reproduce la ventana de día que arma historicos.py al consultar."""
        inicio = datetime.strptime(fecha, "%Y-%m-%d") + timedelta(hours=config.TZ_OFFSET_HOURS)
        return inicio, inicio + timedelta(days=1)

    def test_dato_de_la_tarde_se_encuentra_en_su_dia_local(self):
        # Caso real: snapshot de las 20:20 del 30 ago, guardado como 02:20 UTC
        # del 31. Consultar el 30 tiene que encontrarlo pese al cambio de día.
        guardado = self._guardar("2026-08-30 20:20:59.374")
        assert guardado == datetime(2026, 8, 31, 2, 20, 59, 374000)
        inicio, fin = self._ventana("2026-08-30")
        assert inicio <= guardado < fin

    def test_dato_de_la_manana_se_encuentra_en_su_dia_local(self):
        guardado = self._guardar("2026-08-30 08:15:00.000")
        inicio, fin = self._ventana("2026-08-30")
        assert inicio <= guardado < fin

    def test_dato_no_aparece_en_el_dia_anterior(self):
        guardado = self._guardar("2026-08-30 20:20:59.374")
        inicio, fin = self._ventana("2026-08-29")
        assert not (inicio <= guardado < fin)

    def test_medianoche_local_cae_en_su_dia_y_no_en_el_previo(self):
        # El borde: 00:00:00.001 local del 30 pertenece al 30, no al 29.
        guardado = self._guardar("2026-08-30 00:00:00.001")
        inicio, fin = self._ventana("2026-08-30")
        assert inicio <= guardado < fin
        inicio_prev, fin_prev = self._ventana("2026-08-29")
        assert not (inicio_prev <= guardado < fin_prev)
