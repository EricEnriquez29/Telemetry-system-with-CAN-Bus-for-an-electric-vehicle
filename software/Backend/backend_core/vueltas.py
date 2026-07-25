"""
vueltas.py — Conteo de vueltas por cruce de línea de meta (proyección GPS
a coordenadas cartesianas locales + detección de cruce de segmento) y
estimaciones de sesión (autonomía restante, vuelta más óptima).
"""

import logging
import math

from backend_core import config
from backend_core.estado import estado

logger = logging.getLogger(__name__)


def _to_xy(lat, lon, lat_ref_rad):
    """Proyección equirectangular simple lat/lon → km cartesianos locales."""
    x = config.EARTH_R_KM * math.radians(lon) * math.cos(lat_ref_rad)
    y = config.EARTH_R_KM * math.radians(lat)
    return x, y


def set_meta(lat_a, lon_a, lat_b, lon_b):
    """Setea/actualiza la línea de meta. No resetea n_lap — solo descarta
    la vuelta en curso y reinicia la espera de cruce contra la línea nueva."""
    lat_ref = math.radians((lat_a + lat_b) / 2.0)
    xA, yA = _to_xy(lat_a, lon_a, lat_ref)
    xB, yB = _to_xy(lat_b, lon_b, lat_ref)

    with estado.lock:
        estado.meta_xy = (xA, yA, xB, yB, lat_ref, lat_a, lon_a, lat_b, lon_b)
        estado.d_vuelta = 0.0
        estado.t_vuelta_inicio = None
        estado.ultimo_gps = None
        estado.t_ultimo_cruce = None

    logger.info(f"[META] Línea de meta seteada — A=({lat_a},{lon_a}) B=({lat_b},{lon_b})")


def reset_laps():
    """Reinicia el conteo de vueltas por completo. Se llama al detectar
    transición de sesión inactiva → activa."""
    estado.n_lap = 0
    estado.d_vuelta = 0.0
    estado.t_vuelta_inicio = None
    estado.ultimo_gps = None
    estado.t_ultimo_cruce = None
    estado.d_ref_muestras = []
    estado.d_ref = None
    estado.armado = False
    estado.laps_history = []
    estado.E_HV_lap_inicio = 0.0
    estado.E_regen_lap_inicio = 0.0
    estado.reset_lap_accumulators()
    logger.info("[LAP] Conteo de vueltas reiniciado (nueva sesión activa)")


def compute_lap_estimates(laps_history: list, E_HV_rest) -> dict:
    """Calcula d_rest/n_rest/t_rest (autonomía estimada) y n_opt/score
    (vuelta óptima) a partir de las vueltas completadas de la sesión.
    Requiere al menos 1 vuelta con E_vuelta calculada; si no hay datos
    suficientes, devuelve None en los campos correspondientes."""
    completas = [l for l in laps_history if l.get("E_vuelta") is not None and l.get("d_vuelta", 0) > 0]

    d_rest = n_rest = t_rest = None
    if completas and E_HV_rest is not None:
        etas = [l["E_vuelta"] / l["d_vuelta"] for l in completas]
        eta_sesion_prom = sum(etas) / len(etas)
        d_sesion_prom = sum(l["d_vuelta"] for l in completas) / len(completas)
        t_sesion_prom = sum(l["t_vuelta"] for l in completas) / len(completas)

        if eta_sesion_prom > 0:
            d_rest = round(E_HV_rest / eta_sesion_prom, 2)
            if d_sesion_prom > 0:
                n_rest = round(d_rest / d_sesion_prom, 1)
                t_rest = round(n_rest * t_sesion_prom, 1)

    n_opt = None
    if len(completas) >= 2:
        t_mejor = min(l["t_vuelta"] for l in completas)
        e_min = min(l["E_vuelta"] for l in completas)
        if t_mejor > 0 and e_min > 0:
            mejor_score = None
            for l in completas:
                score = 0.5 * (l["t_vuelta"] / t_mejor) + 0.5 * (l["E_vuelta"] / e_min)
                if mejor_score is None or score < mejor_score:
                    mejor_score = score
                    n_opt = l["n_lap"]

    return {"d_rest": d_rest, "n_rest": n_rest, "t_rest": t_rest, "n_opt": n_opt}


def process_lap(gps_lat: float, gps_lon: float, speed_v: float, now_t: float, sesion_act: bool) -> dict:
    """Evalúa cruce de línea de meta y actualiza n_lap/t_vuelta/d_vuelta.
    El primer cruce válido arma el cronómetro (no cuenta como vuelta);
    los siguientes cierran vueltas. Si la sesión está inactiva o no hay
    línea seteada, congela el estado."""
    if not sesion_act or estado.meta_xy is None:
        return {
            "n_lap": estado.n_lap, "t_vuelta": 0.0, "d_vuelta": round(estado.d_vuelta, 4),
            "laps": list(estado.laps_history), "armado": estado.armado,
        }

    # GPS sin fix válido (0,0) — ignorar este snapshot para el conteo
    if gps_lat == 0.0 and gps_lon == 0.0:
        t_vuelta_actual = round(now_t - estado.t_vuelta_inicio, 1) if estado.t_vuelta_inicio else 0.0
        return {
            "n_lap": estado.n_lap, "t_vuelta": t_vuelta_actual, "d_vuelta": round(estado.d_vuelta, 4),
            "laps": list(estado.laps_history), "armado": estado.armado,
        }

    xA, yA, xB, yB, lat_ref = estado.meta_xy[0], estado.meta_xy[1], estado.meta_xy[2], estado.meta_xy[3], estado.meta_xy[4]
    x, y = _to_xy(gps_lat, gps_lon, lat_ref)

    dx, dy = xB - xA, yB - yA
    seg_len2 = dx * dx + dy * dy
    denom = math.sqrt(seg_len2) if seg_len2 > 0 else 0.0
    d_signed = ((dx * (y - yA)) - (dy * (x - xA))) / denom if denom > 0 else 0.0

    if estado.t_vuelta_inicio is None:
        estado.t_vuelta_inicio = now_t

    estado.d_vuelta += abs(speed_v) * config.DT / 3600.0

    if estado.ultimo_gps is not None:
        x0, y0, d0, t0 = estado.ultimo_gps

        # ── Cambio de signo → candidato a cruce ──
        if d0 * d_signed < 0 and seg_len2 > 0:
            t_proj = ((x - xA) * dx + (y - yA) * dy) / seg_len2

            # ── Cruce dentro del segmento (no su extensión infinita) ──
            if 0.0 <= t_proj <= 1.0:
                debounce_ok = (estado.t_ultimo_cruce is None) or ((now_t - estado.t_ultimo_cruce) > config.LAP_DEBOUNCE)

                if debounce_ok:
                    # ── Interpolar instante exacto de cruce ──
                    frac = abs(d0) / (abs(d0) + abs(d_signed)) if (abs(d0) + abs(d_signed)) > 0 else 0.5
                    t_cruce = t0 + (now_t - t0) * frac

                    # ── Primer cruce: solo arma el cronómetro, no cuenta vuelta ──
                    if not estado.armado:
                        estado.armado = True
                        estado.t_ultimo_cruce = t_cruce
                        estado.t_vuelta_inicio = t_cruce
                        estado.d_vuelta = 0.0
                        estado.ultimo_gps = (x, y, d_signed, now_t)
                        logger.info("[LAP] Primer cruce — cronómetro armado, esperando vuelta 1")
                        return {
                            "n_lap": estado.n_lap, "t_vuelta": 0.0, "d_vuelta": 0.0,
                            "laps": list(estado.laps_history), "armado": estado.armado,
                        }

                    t_vuelta_actual = now_t - estado.t_vuelta_inicio
                    d_valida = True
                    if estado.d_ref is not None:
                        d_valida = (estado.d_ref * (1 - config.LAP_D_TOL)) <= estado.d_vuelta <= (estado.d_ref * (1 + config.LAP_D_TOL))

                    if t_vuelta_actual >= config.LAP_T_MIN and d_valida:
                        estado.n_lap += 1

                        # ── Calibración de distancia de referencia (primeras 5 vueltas) ──
                        if estado.d_ref is None:
                            estado.d_ref_muestras.append(estado.d_vuelta)
                            if len(estado.d_ref_muestras) >= config.LAP_N_CAL:
                                estado.d_ref = sum(estado.d_ref_muestras) / len(estado.d_ref_muestras)
                                logger.info(f"[LAP] Calibración lista — d_ref={estado.d_ref:.3f} km")

                        entry = {
                            "n_lap": estado.n_lap,
                            "t_vuelta": round(t_vuelta_actual, 1),
                            "d_vuelta": round(estado.d_vuelta, 4),
                        }
                        estado.laps_history.append(entry)
                        logger.info(f"[LAP] Vuelta {estado.n_lap} — t={t_vuelta_actual:.1f}s d={estado.d_vuelta:.3f}km")

                        result = {**entry, "laps": list(estado.laps_history), "armado": estado.armado}

                        estado.t_ultimo_cruce = t_cruce
                        estado.t_vuelta_inicio = t_cruce
                        estado.d_vuelta = 0.0
                        estado.ultimo_gps = (x, y, d_signed, now_t)
                        return result
                    else:
                        # ── Cruce rechazado: no cuenta como vuelta, pero SÍ se
                        # actualiza el debounce para no dejarlo "abierto" y que
                        # cruces espurios cercanos se sigan sin filtrar. El
                        # tiempo/distancia de la vuelta en curso NO se reinician,
                        # así el siguiente cruce válido mide correctamente. ──
                        motivo = "t_vuelta<{:.0f}s".format(config.LAP_T_MIN) if t_vuelta_actual < config.LAP_T_MIN else "distancia fuera de ±15% d_ref"
                        logger.info(f"[LAP] Cruce RECHAZADO ({motivo}) — t={t_vuelta_actual:.1f}s d={estado.d_vuelta:.3f}km d_ref={estado.d_ref}")
                        estado.t_ultimo_cruce = t_cruce

    estado.ultimo_gps = (x, y, d_signed, now_t)
    t_vuelta_actual = round(now_t - estado.t_vuelta_inicio, 1) if estado.t_vuelta_inicio else 0.0
    return {
        "n_lap": estado.n_lap, "t_vuelta": t_vuelta_actual, "d_vuelta": round(estado.d_vuelta, 4),
        "laps": list(estado.laps_history), "armado": estado.armado,
    }
