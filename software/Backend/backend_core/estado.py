"""
estado.py — Estado global mutable del backend (una sola sesión de vehículo
a la vez, por diseño: no hay multi-tenant).

Antes cada uno de estos ~45 valores era una variable suelta a nivel de
módulo en fenix_backend.py, y cada función que los tocaba necesitaba
declarar `global _nombre` para poder escribirlos. Aquí viven como atributos
de una única instancia (`estado`) que los demás módulos importan — evita
la lista larga de `global` al inicio de cada función y dificulta que una
variable se use por accidente sin haber sido declarada global primero.

Concurrencia: `mqtt_listener.py` procesa cada mensaje en el hilo del
cliente MQTT, mientras que `meta_server.py` atiende cada request HTTP en
su propio hilo (`ThreadingHTTPServer`). Ambos leen y escriben este mismo
objeto. `estado.lock` (un `RLock`, reentrante para permitir llamadas
anidadas del mismo hilo) protege esa sección: `on_snapshot_message` lo
toma completo, y `vueltas.set_meta` también — así un `POST /set_meta` que
llegue a mitad de un mensaje MQTT espera a que termine, en vez de mezclar
lecturas/escrituras a medias.
"""

import threading


class EstadoBackend:
    def __init__(self):
        # Protege todo el estado de abajo contra acceso concurrente entre
        # el hilo de MQTT (mqtt_listener.py) y los hilos HTTP (meta_server.py).
        self.lock = threading.RLock()

        # ── Sesión / acumuladores de energía ──────────────────────────────
        self.session_id_prev = None
        self.E_HV = 0.0
        self.Q_HV = 0.0
        self.E_regen = 0.0
        self.E_aux = 0.0
        self.Q_aux = 0.0
        self.soc0_aux = None
        self.aux_muestras = []
        self.aux_ultimo_t = None

        # ── Reposo / resistencia interna ──────────────────────────────────
        self.v_rest_pack = None
        self.v_rest_cells = [None] * 16
        self.t_reposo_inicio = None
        self.en_reposo = False

        # ── Salud de batería (SOH) ────────────────────────────────────────
        self.soh_c = None
        self.soh_Q_SOH = 0.0
        self.soh_soc_inicio = None
        self.soh_t_ultimo = None
        self.soh_activo = False

        # ── Orientación IMU (roll/pitch) ──────────────────────────────────
        self.phi_rad = 0.0
        self.theta_rad = 0.0

        # ── Línea de meta / conteo de vueltas ─────────────────────────────
        self.meta_xy = None  # (xA, yA, xB, yB, lat_ref, lat_a, lon_a, lat_b, lon_b) o None
        self.sesion_act_prev = False
        self.n_lap = 0
        self.armado = False  # primer cruce arma el cronómetro, no cuenta como vuelta
        self.laps_history = []  # vueltas cerradas de la sesión actual
        self.t_vuelta_inicio = None
        self.d_vuelta = 0.0
        self.ultimo_gps = None  # (x, y, d_signed, t)
        self.t_ultimo_cruce = None
        self.d_ref_muestras = []
        self.d_ref = None
        self.E_HV_lap_inicio = 0.0
        self.E_regen_lap_inicio = 0.0

        # ── Acumuladores por vuelta (máx/prom dentro de la vuelta en curso) ──
        self.lap_spd_max = 0.0; self.lap_spd_sum = 0.0; self.lap_spd_n = 0
        self.lap_phv_max = 0.0; self.lap_phv_sum = 0.0; self.lap_phv_n = 0
        self.lap_pregen_max = 0.0; self.lap_pregen_sum = 0.0; self.lap_pregen_n = 0
        self.lap_pmec_max = 0.0; self.lap_pmec_sum = 0.0; self.lap_pmec_n = 0
        self.lap_gx_max = 0.0; self.lap_gy_max = 0.0
        self.lap_rpm_max = 0.0; self.lap_rpm_sum = 0.0; self.lap_rpm_n = 0

        # ── Estado de conexión del MGT (vía LWT) ──────────────────────────
        self.mgt_conectado = False
        self.last_snapshot = None  # dict completo {timestamp, vehicle_id, session_id, data}

        # ── Watchdog ───────────────────────────────────────────────────────
        self.watchdog_timer = None

    def reset_lap_accumulators(self):
        """Reinicia los acumuladores máx/prom de la vuelta en curso.
        Se llama al cerrar una vuelta y al reiniciar el conteo completo."""
        self.lap_spd_max = self.lap_spd_sum = 0.0; self.lap_spd_n = 0
        self.lap_phv_max = self.lap_phv_sum = 0.0; self.lap_phv_n = 0
        self.lap_pregen_max = self.lap_pregen_sum = 0.0; self.lap_pregen_n = 0
        self.lap_pmec_max = self.lap_pmec_sum = 0.0; self.lap_pmec_n = 0
        self.lap_gx_max = self.lap_gy_max = 0.0
        self.lap_rpm_max = self.lap_rpm_sum = 0.0; self.lap_rpm_n = 0


# Instancia única del backend — importada por los demás módulos como
# `from backend_core.estado import estado`.
estado = EstadoBackend()
