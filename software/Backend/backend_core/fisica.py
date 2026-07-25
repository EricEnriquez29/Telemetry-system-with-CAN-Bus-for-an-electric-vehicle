"""
fisica.py — Funciones puras de cálculo: eficiencia del tren motriz,
potencias, resistencias internas y orientación IMU (roll/pitch, filtro
complementario). No hace I/O (ni MQTT, ni InfluxDB, ni HTTP) — solo toma
datos y devuelve datos, por eso son fáciles de probar a mano
(ver ../backend-test.py) o con pruebas unitarias reales a futuro.
"""

import math

from backend_core import config
from backend_core.estado import estado


def ocv_to_soc_aux(v: float) -> float:
    """Interpola el % de SOC de la batería auxiliar a partir de su voltaje
    en circuito abierto, usando la tabla de calibración AUX_OCV_TABLE."""
    tabla = config.AUX_OCV_TABLE
    if v <= tabla[0][0]:
        return 0.0
    if v >= tabla[-1][0]:
        return 100.0
    for i in range(len(tabla) - 1):
        v0, s0 = tabla[i]
        v1, s1 = tabla[i + 1]
        if v0 <= v <= v1:
            return s0 + (s1 - s0) * (v - v0) / (v1 - v0)
    return 0.0


def compute_derived(data: dict, soc: float, curr_p: float) -> dict:
    """Calcula las variables derivadas del snapshot MQTT: torque, potencias,
    eficiencias, resistencias internas y orientación (roll/pitch vía filtro
    complementario). Lee/actualiza estado.phi_rad y estado.theta_rad
    (integración del giroscopio, requiere el ángulo anterior) y lee
    estado.v_rest_pack / estado.v_rest_cells (calculados en reposo por
    mqtt_listener.py)."""
    curr_rms = float(data.get("curr_rms", 0))
    rpm = abs(float(data.get("rpm", 0)))
    volt_p = float(data.get("volt_p", 0))
    cell_volts = data.get("cell_volts", [])

    tau_est = config.KT * curr_rms
    p_mec = tau_est * (2 * math.pi * rpm / 60)
    p_hv = (volt_p * abs(curr_p)) if curr_p < -config.I_MIN else None
    p_regen = (volt_p * curr_p) if curr_p > config.I_MIN else None

    if p_hv is not None and p_hv > 300:
        eta = min((p_mec / p_hv) * 100, 100.0)
    else:
        eta = None

    Q_HV_rest = config.Q_NOM * (soc / 100.0)
    E_HV_rest = config.E_NOM * (soc / 100.0)

    r_pack = None
    if estado.v_rest_pack is not None and abs(curr_p) > config.I_MIN:
        r_pack = (estado.v_rest_pack - volt_p) / abs(curr_p)

    # eta_bat: eficiencia batería (sag de voltaje vs. reposo)
    eta_bat = None
    if estado.v_rest_pack is not None and estado.v_rest_pack > 1:
        eta_bat = min((volt_p / estado.v_rest_pack) * 100, 100.0)

    # eta_total: eficiencia total del tren motriz (bat * motor)
    eta_total = None
    if eta is not None and eta_bat is not None:
        eta_total = (eta_bat * eta) / 100.0

    r_cells = {}
    for i, v_load in enumerate(cell_volts):
        v_rest = estado.v_rest_cells[i] if i < len(estado.v_rest_cells) else None
        if v_rest is not None and abs(curr_p) > config.I_MIN:
            r_cells[f"r_cell_{i+1}"] = round((v_rest - float(v_load)) / abs(curr_p), 8)
        else:
            r_cells[f"r_cell_{i+1}"] = None

    acc_x = float(data.get("acc_x", 0))
    acc_y = float(data.get("acc_y", 0))
    acc_z = float(data.get("acc_z", 0))
    gyro_x = float(data.get("gyro_x", 0))
    gyro_y = float(data.get("gyro_y", 0))

    phi_acc = math.atan2(acc_y, acc_z)
    theta_acc = math.atan2(-acc_x, math.sqrt(acc_y**2 + acc_z**2))

    phi_giro = estado.phi_rad + math.radians(gyro_x) * config.DT
    theta_giro = estado.theta_rad + math.radians(gyro_y) * config.DT

    estado.phi_rad = config.ALPHA_CF * phi_giro + (1 - config.ALPHA_CF) * phi_acc
    estado.theta_rad = config.ALPHA_CF * theta_giro + (1 - config.ALPHA_CF) * theta_acc

    phi_deg = math.degrees(estado.phi_rad)
    theta_deg = math.degrees(estado.theta_rad)

    gx = -config.G_CONST * math.sin(estado.theta_rad)
    gy = config.G_CONST * math.sin(estado.phi_rad) * math.cos(estado.theta_rad)
    gz = config.G_CONST * math.cos(estado.phi_rad) * math.cos(estado.theta_rad)

    Gx = ((acc_x * config.G_CONST) - gx) / config.G_CONST
    Gy = ((acc_y * config.G_CONST) - gy) / config.G_CONST
    Gz = ((acc_z * config.G_CONST) - gz) / config.G_CONST

    return {
        "tau_est": round(tau_est, 4),
        "p_mec": round(p_mec, 2),
        "p_hv": round(p_hv, 2) if p_hv is not None else None,
        "p_regen": round(p_regen, 2) if p_regen is not None else None,
        "eta": round(eta, 2) if eta is not None else None,
        "eta_bat": round(eta_bat, 2) if eta_bat is not None else None,
        "eta_total": round(eta_total, 2) if eta_total is not None else None,
        "Q_HV_rest": round(Q_HV_rest, 3),
        "E_HV_rest": round(E_HV_rest, 2),
        "r_pack": round(r_pack, 6) if r_pack is not None else None,
        "r_cells": r_cells,
        "phi": round(phi_deg, 4),
        "theta": round(theta_deg, 4),
        "Gx": round(Gx, 4),
        "Gy": round(Gy, 4),
        "Gz": round(Gz, 4),
        "E_HV": None, "Q_HV": None, "E_regen": None, "soh_c": None,
        "p_aux": None, "E_aux": None, "Q_aux": None, "soc_aux": None,
    }
