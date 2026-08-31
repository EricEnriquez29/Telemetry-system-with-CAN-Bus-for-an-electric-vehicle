"""
historicos.py — Consultas a InfluxDB para sesiones pasadas: resumen
completo de una sesión (usado por el modal de históricos del Frontend) y
lista de sesiones disponibles por fecha.

Estas funciones asumen que `session_id`/`date_str` ya fueron validados por
quien las llama (ver meta_server.py) — igual que un Repository no debería
tener que revalidar lo que ya validó el Controller, pero SÍ es responsable
de nunca insertar esos valores crudos en una consulta sin las comillas
correctas (ver nota de seguridad en build_session_summary).
"""

from datetime import datetime, timedelta

from backend_core import config
from backend_core.influx_client import query_api


def _r(v, dec=None):
    """round() seguro — devuelve None si v es None, evita 'NoneType doesn't define __round__'."""
    return None if v is None else round(v, dec if dec is not None else 0)


def build_session_summary(date_str: str, session_id: str) -> dict:
    """Arma el resumen completo de una sesión: acumulados de batería,
    promedios/máximos de velocidad/potencia/temperatura, top 3 vueltas por
    tiempo/consumo/optimalidad, y la tabla de vueltas completa.

    Nota de seguridad: `session_id` se inserta en la consulta Flux vía
    f-string (Flux no soporta bind params como SQL parametrizado). El
    caller (meta_server.py) DEBE validar que `session_id` solo contenga
    caracteres alfanuméricos/guiones antes de llamar esta función — de lo
    contrario un valor malicioso podría alterar el filtro de la consulta."""
    day_start_local = datetime.strptime(date_str, "%Y-%m-%d") + timedelta(hours=config.TZ_OFFSET_HOURS)
    start = day_start_local.strftime("%Y-%m-%dT%H:%M:%SZ")
    stop_dt = day_start_local + timedelta(days=1)
    stop = stop_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    campos_base = ["soc", "E_HV", "Q_HV", "soc_aux", "E_aux", "Q_aux",
                   "speed_v", "rpm", "Gx", "Gy", "Gz", "p_hv", "p_regen",
                   "p_mec", "tmp_mot", "tmp_cont", "tmp_cap", "tmp_max", "curr_p"]
    filtro_campos = " or ".join([f'r._field == "{c}"' for c in campos_base])

    flux_base = f'''
from(bucket: "{config.INFLUX_BUCKET}")
  |> range(start: {start}, stop: {stop})
  |> filter(fn: (r) => r._measurement == "vehicle_telemetry" and r.session_id == "{session_id}")
  |> filter(fn: (r) => {filtro_campos})
  |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"])
'''

    tables = query_api.query(flux_base, org=config.INFLUX_ORG)

    n = 0
    soc_ini = soc_fin = None
    ehv_ini = ehv_fin = qhv_ini = qhv_fin = None
    socaux_ini = socaux_fin = eaux_ini = eaux_fin = qaux_ini = qaux_fin = None
    spd_sum = spd_max = 0.0
    rpm_sum = rpm_max = 0.0
    gx_max = gy_max = gz_max = 0.0
    phv_sum = phv_max = phv_n = 0.0
    pregen_sum = pregen_max = pregen_n = 0.0
    pmec_sum = pmec_max = 0.0
    tmot_max = tcont_max = tcap_max = tbatt_max = 0.0
    currb_sum = currb_max = currb_n = 0.0
    currr_sum = currr_max = currr_n = 0.0
    t_ini = t_fin = None

    for table in tables:
        for rec in table.records:
            n += 1
            t = rec.get_time()
            if t_ini is None: t_ini = t
            t_fin = t

            def g(field):
                return rec.values.get(field)

            soc = g("soc")
            if soc is not None:
                if soc_ini is None: soc_ini = soc
                soc_fin = soc
            ehv = g("E_HV")
            if ehv is not None:
                if ehv_ini is None: ehv_ini = ehv
                ehv_fin = ehv
            qhv = g("Q_HV")
            if qhv is not None:
                if qhv_ini is None: qhv_ini = qhv
                qhv_fin = qhv
            socaux = g("soc_aux")
            if socaux is not None:
                if socaux_ini is None: socaux_ini = socaux
                socaux_fin = socaux
            eaux = g("E_aux")
            if eaux is not None:
                if eaux_ini is None: eaux_ini = eaux
                eaux_fin = eaux
            qaux = g("Q_aux")
            if qaux is not None:
                if qaux_ini is None: qaux_ini = qaux
                qaux_fin = qaux

            spd = g("speed_v")
            if spd is not None:
                spd_sum += spd; spd_max = max(spd_max, spd)
            rpm_v = g("rpm")
            if rpm_v is not None:
                rpm_v = abs(rpm_v)
                rpm_sum += rpm_v; rpm_max = max(rpm_max, rpm_v)
            gx=g("Gx"); gy=g("Gy"); gz=g("Gz")
            if gx is not None: gx_max = max(gx_max, abs(gx))
            if gy is not None: gy_max = max(gy_max, abs(gy))
            if gz is not None: gz_max = max(gz_max, abs(gz))
            phv = g("p_hv")
            if phv is not None:
                phv_sum += phv; phv_max = max(phv_max, phv); phv_n += 1
            pregen = g("p_regen")
            if pregen is not None:
                pregen_sum += pregen; pregen_max = max(pregen_max, pregen); pregen_n += 1
            pmec = g("p_mec")
            if pmec is not None:
                pmec_sum += pmec; pmec_max = max(pmec_max, pmec)
            for fld, acc in (("tmp_mot","tmot"),("tmp_cont","tcont"),("tmp_cap","tcap"),("tmp_max","tbatt")):
                v = g(fld)
                if v is not None:
                    if acc=="tmot": tmot_max = max(tmot_max, v)
                    elif acc=="tcont": tcont_max = max(tcont_max, v)
                    elif acc=="tcap": tcap_max = max(tcap_max, v)
                    else: tbatt_max = max(tbatt_max, v)
            curr_p = g("curr_p")
            if curr_p is not None:
                if curr_p < 0:
                    v = abs(curr_p); currb_sum += v; currb_max = max(currb_max, v); currb_n += 1
                elif curr_p > 0:
                    currr_sum += curr_p; currr_max = max(currr_max, curr_p); currr_n += 1

    dur_s = (t_fin - t_ini).total_seconds() if (t_ini and t_fin) else 0

    # ── Tabla de vueltas: agrupar por tag lap_number ──
    flux_laps = f'''
from(bucket: "{config.INFLUX_BUCKET}")
  |> range(start: {start}, stop: {stop})
  |> filter(fn: (r) => r._measurement == "vehicle_telemetry" and r.session_id == "{session_id}")
  |> filter(fn: (r) => r._field == "t_vuelta" or r._field == "d_vuelta" or r._field == "E_HV" or r._field == "E_regen" or r._field == "speed_v" or r._field == "p_hv" or r._field == "p_regen" or r._field == "p_mec" or r._field == "Gx" or r._field == "Gy" or r._field == "rpm")
  |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"])
'''
    lap_tables = query_api.query(flux_laps, org=config.INFLUX_ORG)
    lap_groups = {}
    for table in lap_tables:
        for rec in table.records:
            lap_n = rec.values.get("lap_number")
            if lap_n is None: continue
            lap_n = int(lap_n)
            if lap_n == 0: continue
            grp = lap_groups.setdefault(lap_n, {"t":[], "d":[], "ehv":[], "ereg":[],
                "spd":[], "phv":[], "pregen":[], "pmec":[], "gx":[], "gy":[], "rpm":[]})
            v = rec.values
            if v.get("t_vuelta") is not None: grp["t"].append(v["t_vuelta"])
            if v.get("d_vuelta") is not None: grp["d"].append(v["d_vuelta"])
            if v.get("E_HV") is not None: grp["ehv"].append(v["E_HV"])
            if v.get("E_regen") is not None: grp["ereg"].append(v["E_regen"])
            if v.get("speed_v") is not None: grp["spd"].append(abs(v["speed_v"]))
            if v.get("p_hv") is not None: grp["phv"].append(v["p_hv"])
            if v.get("p_regen") is not None: grp["pregen"].append(v["p_regen"])
            if v.get("p_mec") is not None: grp["pmec"].append(v["p_mec"])
            if v.get("Gx") is not None: grp["gx"].append(abs(v["Gx"]))
            if v.get("Gy") is not None: grp["gy"].append(abs(v["Gy"]))
            if v.get("rpm") is not None: grp["rpm"].append(abs(v["rpm"]))

    def maxprom(lst, dec=0):
        if not lst: return (None, None)
        return (_r(max(lst), dec), _r(sum(lst)/len(lst), dec))

    laps = []
    for lap_n in sorted(lap_groups.keys()):
        grp = lap_groups[lap_n]
        if not grp["t"] or not grp["d"]: continue
        t_v = max(grp["t"]); d_v = max(grp["d"])
        e_v = (max(grp["ehv"]) - min(grp["ehv"])) if grp["ehv"] else None
        er_v = (max(grp["ereg"]) - min(grp["ereg"])) if grp["ereg"] else None
        eta_v = _r(e_v / d_v, 2) if (e_v is not None and d_v > 0) else None
        # OJO: estas variables llevan prefijo lap_ a propósito. Antes se
        # llamaban phv_max, pregen_max, pmec_max, gx_max, gy_max y rpm_max —
        # los mismos nombres que los acumuladores del resumen de sesión de
        # más arriba — así que cada vuelta los pisaba, y el resumen acababa
        # devolviendo los máximos de la ÚLTIMA vuelta en vez de los de toda
        # la sesión. Los promedios no se veían afectados porque el resumen
        # los calcula aparte, con sus propios *_sum / *_n.
        lap_vel_max, lap_vel_prom = maxprom(grp["spd"], 1)
        lap_phv_max, lap_phv_prom = maxprom(grp["phv"])
        lap_pregen_max, lap_pregen_prom = maxprom(grp["pregen"])
        lap_pmec_max, lap_pmec_prom = maxprom(grp["pmec"])
        lap_gx_max = _r(max(grp["gx"]), 2) if grp["gx"] else None
        lap_gy_max = _r(max(grp["gy"]), 2) if grp["gy"] else None
        lap_rpm_max, lap_rpm_prom = maxprom(grp["rpm"])
        laps.append({
            "n_lap": lap_n, "t_vuelta": _r(t_v, 1), "d_vuelta": _r(d_v, 4),
            "E_vuelta": _r(e_v, 3) if e_v is not None else None,
            "E_regen_vuelta": _r(er_v, 3) if er_v is not None else None,
            "eta_vuelta": eta_v,
            "vel_max": lap_vel_max, "vel_prom": lap_vel_prom,
            "p_hv_max": lap_phv_max, "p_hv_prom": lap_phv_prom,
            "p_regen_max": lap_pregen_max, "p_regen_prom": lap_pregen_prom,
            "p_mec_max": lap_pmec_max, "p_mec_prom": lap_pmec_prom,
            "Gx_max": lap_gx_max, "Gy_max": lap_gy_max,
            "rpm_max": lap_rpm_max, "rpm_prom": lap_rpm_prom,
        })

    if laps:
        t_mejor_global = min(l["t_vuelta"] for l in laps)
        for l in laps:
            l["delta_mejor"] = _r(l["t_vuelta"] - t_mejor_global, 1)

    top_tiempo = sorted(laps, key=lambda l: l["t_vuelta"])[:3]
    con_e = [l for l in laps if l["E_vuelta"] is not None]
    top_consumo = sorted(con_e, key=lambda l: l["E_vuelta"])[:3]
    top_optimas = []
    if len(con_e) >= 2:
        t_mejor = min(l["t_vuelta"] for l in laps)
        e_min = min(l["E_vuelta"] for l in con_e)
        if t_mejor > 0 and e_min > 0:
            scored = [(0.5*(l["t_vuelta"]/t_mejor) + 0.5*(l["E_vuelta"]/e_min), l) for l in con_e]
            scored.sort(key=lambda x: x[0])
            top_optimas = [{"n_lap": l["n_lap"], "score": _r(s,3)} for s,l in scored[:3]]

    e_vuelta_vals = [l["E_vuelta"] for l in laps if l["E_vuelta"] is not None]
    ereg_vuelta_vals = [l["E_regen_vuelta"] for l in laps if l["E_regen_vuelta"] is not None]

    return {
        "date": date_str, "session_id": session_id,
        "n_vueltas": len(laps), "duracion_s": _r(dur_s, 0),
        "soc_ini": soc_ini, "soc_fin": soc_fin,
        "E_HV_ini": ehv_ini, "E_HV_fin": ehv_fin,
        "Q_HV_ini": qhv_ini, "Q_HV_fin": qhv_fin,
        "soc_aux_ini": socaux_ini, "soc_aux_fin": socaux_fin,
        "E_aux_ini": eaux_ini, "E_aux_fin": eaux_fin,
        "Q_aux_ini": qaux_ini, "Q_aux_fin": qaux_fin,
        "spd_prom": _r(spd_sum/n, 1) if n else None, "spd_max": _r(spd_max, 1),
        "rpm_prom": _r(rpm_sum/n, 0) if n else None, "rpm_max": _r(rpm_max, 0),
        "Gx_max": _r(gx_max, 2), "Gy_max": _r(gy_max, 2), "Gz_max": _r(gz_max, 2),
        "p_hv_prom": _r(phv_sum/phv_n, 1) if phv_n else None, "p_hv_max": _r(phv_max, 1),
        "p_regen_prom": _r(pregen_sum/pregen_n, 1) if pregen_n else None, "p_regen_max": _r(pregen_max, 1),
        "p_mec_prom": _r(pmec_sum/n, 1) if n else None, "p_mec_max": _r(pmec_max, 1),
        "tmp_mot_max": _r(tmot_max,1), "tmp_cont_max": _r(tcont_max,1),
        "tmp_cap_max": _r(tcap_max,1), "tmp_batt_max": _r(tbatt_max,1),
        "curr_batt_prom": _r(currb_sum/currb_n, 1) if currb_n else None, "curr_batt_max": _r(currb_max, 1),
        "curr_regen_prom": _r(currr_sum/currr_n, 1) if currr_n else None, "curr_regen_max": _r(currr_max, 1),
        "E_vuelta_prom": _r(sum(e_vuelta_vals)/len(e_vuelta_vals), 2) if e_vuelta_vals else None,
        "E_regen_vuelta_prom": _r(sum(ereg_vuelta_vals)/len(ereg_vuelta_vals), 2) if ereg_vuelta_vals else None,
        "top_tiempo": top_tiempo, "top_consumo": top_consumo, "top_optimas": top_optimas,
        "laps": laps,
    }


def get_sessions_for_date(date_str: str) -> list:
    """Devuelve la lista de session_id distintos con datos en ese día."""
    day_start_local = datetime.strptime(date_str, "%Y-%m-%d") + timedelta(hours=config.TZ_OFFSET_HOURS)
    start = day_start_local.strftime("%Y-%m-%dT%H:%M:%SZ")
    stop_dt = day_start_local + timedelta(days=1)
    stop = stop_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    flux = f'''
from(bucket: "{config.INFLUX_BUCKET}")
  |> range(start: {start}, stop: {stop})
  |> filter(fn: (r) => r._measurement == "vehicle_telemetry")
  |> keep(columns: ["session_id"])
  |> distinct(column: "session_id")
'''
    tables = query_api.query(flux, org=config.INFLUX_ORG)
    sesiones = set()
    for table in tables:
        for rec in table.records:
            v = rec.get_value()
            if v is not None:
                sesiones.add(str(v))
    return sorted(sesiones, key=lambda s: int(s) if s.isdigit() else s)
