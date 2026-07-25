"""
mqtt_listener.py — Orquestador: escucha MQTT, llama a fisica.py y
vueltas.py para calcular las variables derivadas, escribe cada snapshot en
InfluxDB, y lo reenvía a fenix_api.py (que a su vez lo empuja por
WebSocket al Frontend). Es el equivalente de dashboard-render.js del
Frontend: el único módulo que conoce a todos los demás.
"""

import json
import logging
import threading
import time
from datetime import datetime, timezone, timedelta

import paho.mqtt.client as mqtt
import requests
from influxdb_client import Point, WritePrecision

from backend_core import config, fisica, vueltas
from backend_core.estado import estado
from backend_core.influx_client import write_api
from backend_core.meta_server import start_meta_server

logger = logging.getLogger(__name__)


# ─── Watchdog ─────────────────────────────────────────────────────────────
def send_zero_snapshot():
    """Envía snapshot con todo en cero cuando no hay datos MQTT."""
    logger.warning("[WD] Sin datos MQTT — enviando snapshot cero")
    ts_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    snapshot = {
        "timestamp": ts_now,
        "vehicle_id": "25",
        "session_id": estado.session_id_prev or "0",
        "data": {
            "curr_rms": 0.0, "speed_v": 0.0, "odo_veh": 0.0,
            "tmp_mot": 0.0, "tmp_cont": 0.0, "tmp_cap": 0.0,
            "mot_torq": 0.0, "batt_curr": 0.0, "rpm": 0.0,
            "throttle": 0.0, "brake": 0.0, "cont_st": 0.0,
            "ksy_v": 0.0, "volt_p": 0.0, "curr_p": 0.0,
            "soc": 0.0, "tmp_max": 0.0, "tmp_min": 0.0,
            "gps_lat": 0.0, "gps_lon": 0.0,
            "acc_x": 0.0, "acc_y": 0.0, "acc_z": 0.0,
            "gyro_x": 0.0, "gyro_y": 0.0, "gyro_z": 0.0,
            "volt_a": 0.0, "curr_a": 0.0,
            "cells": {f"cell_{i+1}": 0.0 for i in range(16)},
            "tau_est": 0.0, "p_mec": 0.0, "p_hv": None,
            "p_regen": None, "eta": None, "eta_bat": None, "eta_total": None,
            "E_HV": 0.0,
            "Q_HV": 0.0,
            "E_regen": 0.0,
            "Q_HV_rest": 0.0, "E_HV_rest": 0.0,
            "r_pack": None,
            "r_cells": {f"r_cell_{i+1}": None for i in range(16)},
            "soh_c": round(estado.soh_c, 2) if estado.soh_c is not None else None,
            "soh_activo": False, "soh_Q_SOH": 0.0, "soh_soc_inicio": None,
            "p_aux": 0.0,
            "E_aux": 0.0,
            "Q_aux": 0.0,
            "soc_aux": None,
            "v_rest_pack": estado.v_rest_pack, "t_reposo_s": 0,
            "phi": 0.0, "theta": 0.0,
            "Gx": 0.0, "Gy": 0.0, "Gz": 0.0,
            "n_lap": estado.n_lap, "t_vuelta": 0.0, "d_vuelta": round(estado.d_vuelta, 4),
            "laps": list(estado.laps_history),
            "armado": False,
            "mgt_conectado": estado.mgt_conectado,
            "d_rest": None, "n_rest": None, "t_rest": None, "n_opt": None,
            "E_vuelta_actual": None, "E_regen_vuelta_actual": None,
            "vel_max_actual": None, "vel_prom_actual": None,
            "p_hv_max_actual": None, "p_hv_prom_actual": None,
            "p_regen_max_actual": None, "p_regen_prom_actual": None,
            "p_mec_max_actual": None, "p_mec_prom_actual": None,
            "Gx_max_actual": None, "Gy_max_actual": None,
            "rpm_max_actual": None, "rpm_prom_actual": None,
            "sesion_act": False,
            "meta_lat_a": estado.meta_xy[5] if estado.meta_xy else None,
            "meta_lon_a": estado.meta_xy[6] if estado.meta_xy else None,
            "meta_lat_b": estado.meta_xy[7] if estado.meta_xy else None,
            "meta_lon_b": estado.meta_xy[8] if estado.meta_xy else None,
        }
    }
    try:
        requests.post(config.API_INTERNAL_URL, json=snapshot, timeout=0.5)
    except Exception as e:
        logger.error(f"[WD] Error POST: {e}")

    # ── Reprogramar: threading.Timer es de un solo disparo. Si seguimos sin
    # datos MQTT, esto vuelve a llamar send_zero_snapshot() en WATCHDOG_TIMEOUT
    # segundos, repitiendo hasta que llegue un mensaje real (que reprograma
    # el watchdog normalmente vía reset_watchdog() en on_snapshot_message). ──
    reset_watchdog()


def reset_watchdog():
    """Reinicia el timer del watchdog. Llamar en cada on_message."""
    if estado.watchdog_timer is not None:
        estado.watchdog_timer.cancel()
    estado.watchdog_timer = threading.Timer(config.WATCHDOG_TIMEOUT, send_zero_snapshot)
    estado.watchdog_timer.daemon = True
    estado.watchdog_timer.start()


# ─── Callbacks MQTT ───────────────────────────────────────────────────────
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logger.info("Conectado al broker MQTT")
        client.subscribe(config.MQTT_TOPIC)
        client.subscribe(config.MQTT_STATUS_TOPIC)
        logger.info(f"Suscrito a {config.MQTT_TOPIC} y {config.MQTT_STATUS_TOPIC}")
    else:
        logger.error(f"Error de conexion MQTT: rc={rc}")


def push_snapshot_now():
    """Reenvía el último snapshot conocido con el estado de conexión del MGT
    actualizado. Se usa cuando cambia sesion_act/LWT sin esperar el próximo dato."""
    if estado.last_snapshot is None:
        return
    snap = dict(estado.last_snapshot)
    snap["data"] = dict(snap["data"])
    snap["data"]["mgt_conectado"] = estado.mgt_conectado
    snap["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    try:
        requests.post(config.API_INTERNAL_URL, json=snap, timeout=0.5)
    except Exception as e:
        logger.error(f"[MGT] Error POST estado: {e}")


def on_status_message(msg):
    """Callback para el tópico fenix/mgt/status (LWT: 'online' / 'offline')."""
    try:
        payload = msg.payload.decode().strip().lower()
    except Exception:
        payload = ""
    nuevo_estado = (payload == "online")
    if nuevo_estado != estado.mgt_conectado:
        estado.mgt_conectado = nuevo_estado
        logger.info(f"[MGT] Estado → {'conectado' if estado.mgt_conectado else 'DESCONECTADO'}")
        if not estado.mgt_conectado:
            send_zero_snapshot()
        # al reconectar NO reenviamos el último snapshot cacheado (son datos
        # congelados de antes de la caída) — esperamos el primer dato real nuevo


def on_message(client, userdata, msg):
    if msg.topic == config.MQTT_STATUS_TOPIC:
        on_status_message(msg)
        return
    on_snapshot_message(client, userdata, msg)


def on_snapshot_message(client, userdata, msg):
    # ── Watchdog: llegó un mensaje, reiniciar timer ───────────────────────────
    reset_watchdog()

    # ── Lock: todo este bloque toca estado.* — evita que un POST /set_meta
    # concurrente (hilo HTTP de meta_server.py) lea/escriba a medias mientras
    # este mensaje se procesa. acquire/release manual (en vez de "with") para
    # no tener que reindentar las ~350 líneas de este bloque. ──
    estado.lock.acquire()
    try:
        data = json.loads(msg.payload.decode())

        # ── 0. Validar formato y campos obligatorios ──────────────────────────
        campos_obligatorios = ("veh_id", "sess_id", "times")
        faltantes = [c for c in campos_obligatorios if c not in data]
        if faltantes:
            logger.error(f"[ERROR] Mensaje MQTT sin campos obligatorios: {faltantes}")
            return

        curr_p = float(data.get("curr_p", 0))
        soc = float(data.get("soc", 0))
        volt_p = float(data.get("volt_p", 0))
        cell_volts = data.get("cell_volts", [])

        # ── 1. Detectar cambio de sesión (fecha + sess_id, evita choques entre días) ──
        fecha_hoy = str(data.get("times", ""))[:10]
        new_session_id = f"{fecha_hoy}_{data.get('sess_id', 0)}"
        if new_session_id != estado.session_id_prev:
            logger.info(f"[Sesión] {estado.session_id_prev} → {new_session_id} — reiniciando acumuladores")
            estado.session_id_prev = new_session_id
            estado.E_HV = estado.Q_HV = estado.E_regen = estado.E_aux = estado.Q_aux = 0.0
            estado.soc0_aux = None; estado.aux_muestras = []; estado.aux_ultimo_t = None
            estado.soh_Q_SOH = 0.0; estado.soh_soc_inicio = None
            estado.soh_t_ultimo = None; estado.soh_activo = False
            estado.phi_rad = 0.0; estado.theta_rad = 0.0

        # ── 1b. Estado de sesión activa (lo calcula el MGT, no se infiere aquí) ──
        sesion_act = bool(data.get("sesion_act", False))
        if sesion_act and not estado.sesion_act_prev:
            vueltas.reset_laps()
        estado.sesion_act_prev = sesion_act

        # ── 2. Lógica de reposo para V_rest ──────────────────────────────────
        now = time.time()
        if abs(curr_p) < config.I_MIN:
            if not estado.en_reposo:
                estado.en_reposo = True; estado.t_reposo_inicio = now
            else:
                if (now - estado.t_reposo_inicio) >= config.T_REPOSO:
                    estado.v_rest_pack = volt_p
                    estado.v_rest_cells = [float(v) for v in cell_volts] if cell_volts else estado.v_rest_cells
        else:
            estado.en_reposo = False

        # ── 3. Calcular variables derivadas ───────────────────────────────────
        derived = fisica.compute_derived(data, soc, curr_p)

        # ── 3b. Conteo de vueltas ──────────────────────────────────────────────
        gps_lat = float(data.get("gps_lat", 0))
        gps_lon = float(data.get("gps_lon", 0))
        speed_v = float(data.get("speed_v", 0))
        n_lap_antes = estado.n_lap
        armado_antes = estado.armado
        lap_info = vueltas.process_lap(gps_lat, gps_lon, speed_v, now, sesion_act)
        derived["n_lap"] = lap_info["n_lap"]
        derived["t_vuelta"] = lap_info["t_vuelta"]
        derived["d_vuelta"] = lap_info["d_vuelta"]
        derived["laps"] = lap_info["laps"]
        derived["armado"] = lap_info["armado"]

        # ── Primer cruce (recién armado): marca el inicio de la vuelta 1 ───────
        if lap_info["armado"] and not armado_antes:
            estado.E_HV_lap_inicio = estado.E_HV
            estado.E_regen_lap_inicio = estado.E_regen

        # ── Acumular estadísticas de la vuelta en curso (máx/prom dentro de la vuelta) ──
        if lap_info["armado"]:
            spd_v = abs(speed_v)
            estado.lap_spd_max = max(estado.lap_spd_max, spd_v); estado.lap_spd_sum += spd_v; estado.lap_spd_n += 1
            if derived.get("p_hv") is not None:
                estado.lap_phv_max = max(estado.lap_phv_max, derived["p_hv"]); estado.lap_phv_sum += derived["p_hv"]; estado.lap_phv_n += 1
            if derived.get("p_regen") is not None:
                estado.lap_pregen_max = max(estado.lap_pregen_max, derived["p_regen"]); estado.lap_pregen_sum += derived["p_regen"]; estado.lap_pregen_n += 1
            estado.lap_pmec_max = max(estado.lap_pmec_max, derived["p_mec"]); estado.lap_pmec_sum += derived["p_mec"]; estado.lap_pmec_n += 1
            estado.lap_gx_max = max(estado.lap_gx_max, abs(derived["Gx"]))
            estado.lap_gy_max = max(estado.lap_gy_max, abs(derived["Gy"]))
            rpm_v = abs(float(data.get("rpm", 0)))
            estado.lap_rpm_max = max(estado.lap_rpm_max, rpm_v); estado.lap_rpm_sum += rpm_v; estado.lap_rpm_n += 1

        # ── Vuelta recién completada: energía consumida/regenerada en esa vuelta ──
        if lap_info["n_lap"] > n_lap_antes and estado.laps_history:
            e_vuelta = round(estado.E_HV - estado.E_HV_lap_inicio, 3)
            e_regen_vuelta = round(estado.E_regen - estado.E_regen_lap_inicio, 3)
            entry = estado.laps_history[-1]
            entry["E_vuelta"] = e_vuelta
            entry["E_regen_vuelta"] = e_regen_vuelta
            entry["eta_vuelta"] = (
                round(e_vuelta / entry["d_vuelta"], 2)
                if entry["d_vuelta"] > 0 else None
            )
            entry["vel_max"] = round(estado.lap_spd_max, 1)
            entry["vel_prom"] = round(estado.lap_spd_sum / estado.lap_spd_n, 1) if estado.lap_spd_n else None
            entry["p_hv_max"] = round(estado.lap_phv_max, 0) if estado.lap_phv_n else None
            entry["p_hv_prom"] = round(estado.lap_phv_sum / estado.lap_phv_n, 0) if estado.lap_phv_n else None
            entry["p_regen_max"] = round(estado.lap_pregen_max, 0) if estado.lap_pregen_n else None
            entry["p_regen_prom"] = round(estado.lap_pregen_sum / estado.lap_pregen_n, 0) if estado.lap_pregen_n else None
            entry["p_mec_max"] = round(estado.lap_pmec_max, 0)
            entry["p_mec_prom"] = round(estado.lap_pmec_sum / estado.lap_pmec_n, 0) if estado.lap_pmec_n else None
            entry["Gx_max"] = round(estado.lap_gx_max, 2)
            entry["Gy_max"] = round(estado.lap_gy_max, 2)
            entry["rpm_max"] = round(estado.lap_rpm_max, 0)
            entry["rpm_prom"] = round(estado.lap_rpm_sum / estado.lap_rpm_n, 0) if estado.lap_rpm_n else None

            # ── Δ vs mejor tiempo — recalcular para todas las vueltas ──────────
            t_mejor = min(l["t_vuelta"] for l in estado.laps_history)
            for l in estado.laps_history:
                l["delta_mejor"] = round(l["t_vuelta"] - t_mejor, 1)

            derived["laps"] = list(estado.laps_history)
            estado.E_HV_lap_inicio = estado.E_HV
            estado.E_regen_lap_inicio = estado.E_regen
            estado.reset_lap_accumulators()

        # ── Estadísticas en vivo de la vuelta en curso (aún sin cerrar) ────────
        derived["vel_max_actual"] = round(estado.lap_spd_max, 1)
        derived["vel_prom_actual"] = round(estado.lap_spd_sum/estado.lap_spd_n, 1) if estado.lap_spd_n else None
        derived["p_hv_max_actual"] = round(estado.lap_phv_max, 0) if estado.lap_phv_n else None
        derived["p_hv_prom_actual"] = round(estado.lap_phv_sum/estado.lap_phv_n, 0) if estado.lap_phv_n else None
        derived["p_regen_max_actual"] = round(estado.lap_pregen_max, 0) if estado.lap_pregen_n else None
        derived["p_regen_prom_actual"] = round(estado.lap_pregen_sum/estado.lap_pregen_n, 0) if estado.lap_pregen_n else None
        derived["p_mec_max_actual"] = round(estado.lap_pmec_max, 0)
        derived["p_mec_prom_actual"] = round(estado.lap_pmec_sum/estado.lap_pmec_n, 0) if estado.lap_pmec_n else None
        derived["Gx_max_actual"] = round(estado.lap_gx_max, 2)
        derived["Gy_max_actual"] = round(estado.lap_gy_max, 2)
        derived["rpm_max_actual"] = round(estado.lap_rpm_max, 0)
        derived["rpm_prom_actual"] = round(estado.lap_rpm_sum/estado.lap_rpm_n, 0) if estado.lap_rpm_n else None

        # ── Estimaciones de sesión: autonomía y vuelta óptima ──────────────────
        estim = vueltas.compute_lap_estimates(estado.laps_history, derived.get("E_HV_rest"))
        derived.update(estim)

        # ── Energía de la vuelta en curso (se actualiza cada snapshot, no solo al cerrar) ──
        if lap_info["armado"]:
            derived["E_vuelta_actual"] = round(estado.E_HV - estado.E_HV_lap_inicio, 3)
            derived["E_regen_vuelta_actual"] = round(estado.E_regen - estado.E_regen_lap_inicio, 3)
        else:
            derived["E_vuelta_actual"] = None
            derived["E_regen_vuelta_actual"] = None

        # ── 4. Actualizar acumuladores HV ─────────────────────────────────────
        if curr_p < -config.I_MIN and derived["p_hv"] is not None:
            estado.E_HV += derived["p_hv"] * config.DT / 3600.0
        if curr_p < -config.I_MIN:
            estado.Q_HV += abs(curr_p) * config.DT / 3600.0
        if curr_p > config.I_MIN and derived["p_regen"] is not None:
            estado.E_regen += derived["p_regen"] * config.DT / 3600.0

        derived["E_HV"] = round(estado.E_HV, 3)
        derived["Q_HV"] = round(estado.Q_HV, 4)
        derived["E_regen"] = round(estado.E_regen, 3)

        # ── 5. Sistema auxiliar ───────────────────────────────────────────────
        volt_a = float(data.get("volt_a", 0))
        curr_a = float(data.get("curr_a", 0))
        p_aux = volt_a * curr_a
        estado.E_aux += p_aux * config.DT / 3600.0
        estado.Q_aux += curr_a * config.DT / 3600.0

        if estado.soc0_aux is None and len(estado.aux_muestras) < 4:
            if estado.aux_ultimo_t is None or (now - estado.aux_ultimo_t) >= 1.0:
                if curr_a > 0.0 and volt_a > 10.0:
                    estado.aux_muestras.append((curr_a, volt_a))
                    estado.aux_ultimo_t = now
                    logger.info(f"[AUX] Muestra {len(estado.aux_muestras)}/4 — curr_a={curr_a:.2f}A volt_a={volt_a:.3f}V")
                else:
                    logger.info(f"[AUX] Muestra descartada — curr_a={curr_a:.2f}A volt_a={volt_a:.3f}V")
                    estado.aux_ultimo_t = now
            if len(estado.aux_muestras) == 4:
                min_curr, volt_ocv = min(estado.aux_muestras, key=lambda x: x[0])
                estado.soc0_aux = fisica.ocv_to_soc_aux(volt_ocv)
                logger.info(f"[AUX] SOC0 = {estado.soc0_aux:.1f}%")

        soc_aux = max(0.0, estado.soc0_aux - (estado.Q_aux / config.Q_NOM_AUX) * 100.0) if estado.soc0_aux is not None else None
        derived["p_aux"] = round(p_aux, 2)
        derived["E_aux"] = round(estado.E_aux, 3)
        derived["Q_aux"] = round(estado.Q_aux, 4)
        derived["soc_aux"] = round(soc_aux, 2) if soc_aux is not None else None

        # ── 6. Lógica SOH ─────────────────────────────────────────────────────
        if curr_p < -config.I_MIN:
            if not estado.soh_activo:
                estado.soh_activo = True; estado.soh_Q_SOH = 0.0; estado.soh_soc_inicio = soc
                logger.info(f"[SOH] Inicio intervalo — SOC_inicio={soc:.1f}%")
            elif estado.soh_soc_inicio is not None and estado.soh_soc_inicio < 1.0 and soc > 1.0:
                estado.soh_soc_inicio = soc; estado.soh_Q_SOH = 0.0
                logger.info(f"[SOH] SOC_inicio corregido a {soc:.1f}%")
            if estado.soh_t_ultimo is not None and (now - estado.soh_t_ultimo) > config.T_GAP_MAX:
                logger.info("[SOH] Gap superado — reiniciando")
                estado.soh_activo = False; estado.soh_Q_SOH = 0.0; estado.soh_soc_inicio = soc
            else:
                estado.soh_Q_SOH += abs(curr_p) * config.DT / 3600.0
            estado.soh_t_ultimo = now
            if estado.soh_soc_inicio is not None:
                delta_soc = estado.soh_soc_inicio - soc
                if delta_soc >= config.SOC_MIN_DELTA:
                    Q_teorico = config.Q_NOM * (delta_soc / 100.0)
                    estado.soh_c = round((estado.soh_Q_SOH / Q_teorico) * 100.0, 2)
                    logger.info(f"[SOH] SOH={estado.soh_c:.2f}%")
                    estado.soh_activo = False; estado.soh_Q_SOH = 0.0; estado.soh_soc_inicio = None

        derived["soh_c"] = round(estado.soh_c, 2) if estado.soh_c is not None else None

        # ── 7. Escribir en InfluxDB ───────────────────────────────────────────
        ts = datetime.strptime(data["times"], "%Y-%m-%d %H:%M:%S.%f").replace(
            tzinfo=timezone(timedelta(hours=-6))
        )

        point = (
            Point("vehicle_telemetry")
            .tag("vehicle_id", str(data.get("veh_id", 25)))
            .tag("session_id", str(data.get("sess_id", 0)))
            .tag("lap_number", str(derived["n_lap"]))
            .time(ts, WritePrecision.MS)
            .field("curr_rms", float(data.get("curr_rms", 0)))
            .field("speed_v", float(data.get("speed_v", 0)))
            .field("odo_veh", float(data.get("odo_veh", 0)))
            .field("tmp_mot", float(data.get("tmp_mot", 0)))
            .field("tmp_cont", float(data.get("tmp_cont", 0)))
            .field("tmp_cap", float(data.get("tmp_cap", 0)))
            .field("mot_torq", float(data.get("mot_torq", 0)))
            .field("batt_curr", float(data.get("batt_curr", 0)))
            .field("rpm", float(data.get("rpm", 0)))
            .field("throttle", float(data.get("throttle", 0)))
            .field("brake", float(data.get("brake", 0)))
            .field("cont_st", float(data.get("cont_st", 0)))
            .field("ksy_v", float(data.get("ksy_v", 0)))
            .field("volt_p", float(data.get("volt_p", 0)))
            .field("curr_p", float(data.get("curr_p", 0)))
            .field("soc", float(data.get("soc", 0)))
            .field("tmp_max", float(data.get("tmp_max", 0)))
            .field("tmp_min", float(data.get("tmp_min", 0)))
            .field("gps_lat", float(data.get("gps_lat", 0)))
            .field("gps_lon", float(data.get("gps_lon", 0)))
            .field("acc_x", float(data.get("acc_x", 0)))
            .field("acc_y", float(data.get("acc_y", 0)))
            .field("acc_z", float(data.get("acc_z", 0)))
            .field("gyro_x", float(data.get("gyro_x", 0)))
            .field("gyro_y", float(data.get("gyro_y", 0)))
            .field("gyro_z", float(data.get("gyro_z", 0)))
            .field("volt_a", float(data.get("volt_a", 0)))
            .field("curr_a", float(data.get("curr_a", 0)))
            .field("tau_est", derived["tau_est"])
            .field("p_mec", derived["p_mec"])
            .field("E_HV", derived["E_HV"])
            .field("Q_HV", derived["Q_HV"])
            .field("E_regen", derived["E_regen"])
            .field("Q_HV_rest", derived["Q_HV_rest"])
            .field("E_HV_rest", derived["E_HV_rest"])
            .field("p_aux", derived["p_aux"])
            .field("E_aux", derived["E_aux"])
            .field("Q_aux", derived["Q_aux"])
            .field("phi", derived["phi"])
            .field("theta", derived["theta"])
            .field("Gx", derived["Gx"])
            .field("Gy", derived["Gy"])
            .field("Gz", derived["Gz"])
            .field("t_vuelta", derived["t_vuelta"])
            .field("d_vuelta", derived["d_vuelta"])
        )

        if derived["soc_aux"] is not None: point = point.field("soc_aux", derived["soc_aux"])
        if derived["p_hv"] is not None: point = point.field("p_hv", derived["p_hv"])
        if derived["p_regen"] is not None: point = point.field("p_regen", derived["p_regen"])
        if derived["eta"] is not None: point = point.field("eta", derived["eta"])
        if derived["eta_bat"] is not None: point = point.field("eta_bat", derived["eta_bat"])
        if derived["eta_total"] is not None: point = point.field("eta_total", derived["eta_total"])
        if derived["r_pack"] is not None: point = point.field("r_pack", derived["r_pack"])
        if derived["soh_c"] is not None: point = point.field("soh_c", derived["soh_c"])

        for i, v in enumerate(cell_volts):
            point = point.field(f"cell_{i+1}", float(v))
        for i in range(16):
            val = derived["r_cells"].get(f"r_cell_{i+1}")
            if val is not None: point = point.field(f"r_cell_{i+1}", val)

        # ── Try/except propio: si InfluxDB falla (caído, timeout, red), el
        # resto de la función (empaquetar y reenviar al Frontend) debe seguir
        # corriendo igual. Antes esta escritura compartía el try/except de
        # toda la función, así que un InfluxDB caído dejaba el dashboard
        # congelado aunque el MQTT siguiera llegando bien. ──
        try:
            write_api.write(bucket=config.INFLUX_BUCKET, org=config.INFLUX_ORG, record=point)
            logger.info(f"[InfluxDB] sess={data.get('sess_id')} t={data.get('times')} guardado")
        except Exception as influx_err:
            logger.error(f"[InfluxDB] Error al escribir: {influx_err}")

        # ── 8. Empaquetar snapshot para fenix_api ─────────────────────────────
        snapshot = {
            "timestamp": data.get("times"),
            "vehicle_id": str(data.get("veh_id", 25)),
            "session_id": str(data.get("sess_id", 0)),
            "data": {
                "curr_rms": float(data.get("curr_rms", 0)),
                "speed_v": float(data.get("speed_v", 0)),
                "odo_veh": float(data.get("odo_veh", 0)),
                "tmp_mot": float(data.get("tmp_mot", 0)),
                "tmp_cont": float(data.get("tmp_cont", 0)),
                "tmp_cap": float(data.get("tmp_cap", 0)),
                "mot_torq": float(data.get("mot_torq", 0)),
                "batt_curr": float(data.get("batt_curr", 0)),
                "rpm": float(data.get("rpm", 0)),
                "throttle": float(data.get("throttle", 0)),
                "brake": float(data.get("brake", 0)),
                "cont_st": float(data.get("cont_st", 0)),
                "ksy_v": float(data.get("ksy_v", 0)),
                "volt_p": float(data.get("volt_p", 0)),
                "curr_p": float(data.get("curr_p", 0)),
                "soc": float(data.get("soc", 0)),
                "tmp_max": float(data.get("tmp_max", 0)),
                "tmp_min": float(data.get("tmp_min", 0)),
                "gps_lat": float(data.get("gps_lat", 0)),
                "gps_lon": float(data.get("gps_lon", 0)),
                "acc_x": float(data.get("acc_x", 0)),
                "acc_y": float(data.get("acc_y", 0)),
                "acc_z": float(data.get("acc_z", 0)),
                "gyro_x": float(data.get("gyro_x", 0)),
                "gyro_y": float(data.get("gyro_y", 0)),
                "gyro_z": float(data.get("gyro_z", 0)),
                "volt_a": float(data.get("volt_a", 0)),
                "curr_a": float(data.get("curr_a", 0)),
                "cells": {f"cell_{i+1}": float(v) for i, v in enumerate(cell_volts)},
                "tau_est": derived["tau_est"],
                "p_mec": derived["p_mec"],
                "p_hv": derived["p_hv"],
                "p_regen": derived["p_regen"],
                "eta": derived["eta"],
                "eta_bat": derived["eta_bat"],
                "eta_total": derived["eta_total"],
                "E_HV": derived["E_HV"],
                "Q_HV": derived["Q_HV"],
                "E_regen": derived["E_regen"],
                "Q_HV_rest": derived["Q_HV_rest"],
                "E_HV_rest": derived["E_HV_rest"],
                "r_pack": derived["r_pack"],
                "r_cells": derived["r_cells"],
                "soh_c": derived["soh_c"],
                "soh_activo": estado.soh_activo,
                "soh_Q_SOH": round(estado.soh_Q_SOH, 4),
                "soh_soc_inicio": estado.soh_soc_inicio,
                "p_aux": derived["p_aux"],
                "E_aux": derived["E_aux"],
                "Q_aux": derived["Q_aux"],
                "soc_aux": derived["soc_aux"],
                "v_rest_pack": estado.v_rest_pack,
                "t_reposo_s": round(time.time() - estado.t_reposo_inicio, 1) if estado.en_reposo and estado.t_reposo_inicio else 0,
                "phi": derived["phi"],
                "theta": derived["theta"],
                "Gx": derived["Gx"],
                "Gy": derived["Gy"],
                "Gz": derived["Gz"],
                "n_lap": derived["n_lap"],
                "t_vuelta": derived["t_vuelta"],
                "d_vuelta": derived["d_vuelta"],
                "laps": derived["laps"],
                "armado": derived["armado"],
                "E_vuelta_actual": derived["E_vuelta_actual"],
                "E_regen_vuelta_actual": derived["E_regen_vuelta_actual"],
                "vel_max_actual": derived["vel_max_actual"],
                "vel_prom_actual": derived["vel_prom_actual"],
                "p_hv_max_actual": derived["p_hv_max_actual"],
                "p_hv_prom_actual": derived["p_hv_prom_actual"],
                "p_regen_max_actual": derived["p_regen_max_actual"],
                "p_regen_prom_actual": derived["p_regen_prom_actual"],
                "p_mec_max_actual": derived["p_mec_max_actual"],
                "p_mec_prom_actual": derived["p_mec_prom_actual"],
                "Gx_max_actual": derived["Gx_max_actual"],
                "Gy_max_actual": derived["Gy_max_actual"],
                "rpm_max_actual": derived["rpm_max_actual"],
                "rpm_prom_actual": derived["rpm_prom_actual"],
                "d_rest": derived["d_rest"],
                "n_rest": derived["n_rest"],
                "t_rest": derived["t_rest"],
                "n_opt": derived["n_opt"],
                "sesion_act": sesion_act,
                "mgt_conectado": estado.mgt_conectado,
                "meta_lat_a": estado.meta_xy[5] if estado.meta_xy else None,
                "meta_lon_a": estado.meta_xy[6] if estado.meta_xy else None,
                "meta_lat_b": estado.meta_xy[7] if estado.meta_xy else None,
                "meta_lon_b": estado.meta_xy[8] if estado.meta_xy else None,
            }
        }

        estado.last_snapshot = snapshot
        try:
            requests.post(config.API_INTERNAL_URL, json=snapshot, timeout=0.5)
        except Exception as api_err:
            logger.error(f"[API push] {api_err}")

    except Exception as e:
        logger.error(f"[ERROR on_message] {e}")
    finally:
        estado.lock.release()


# ─── Main ─────────────────────────────────────────────────────────────────
def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(config.MQTT_USER, config.MQTT_PASS)
    client.on_connect = on_connect
    client.on_message = on_message

    start_meta_server()

    logger.info("Conectando al broker MQTT...")
    client.connect(config.MQTT_HOST, config.MQTT_PORT, keepalive=60)

    # Iniciar watchdog desde el arranque
    reset_watchdog()

    client.loop_forever()
