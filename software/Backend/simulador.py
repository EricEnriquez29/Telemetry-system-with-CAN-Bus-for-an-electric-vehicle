"""
simulador.py  –  Escudería Fénix
Interfaz tkinter con sliders de Throttle y Brake.
Calcula 44 variables del vehículo y las manda a fenix_api a 10Hz.

Uso:
    pip install requests
    python simulador.py
"""

import requests
import time
import math
import random
import threading
import tkinter as tk
from datetime import datetime

API_URL  = "http://localhost:8050/internal/snapshot"
INTERVAL = 0.1  # 10 Hz

# ─── Estado compartido entre tkinter y el loop ────────────────────────────────
state = {
    "throttle": 0.0,   # 0-100 %
    "brake":    0.0,   # 0-100 %
}

# ─── Variables de estado del vehículo (con inercia) ───────────────────────────
veh = {
    "rpm":      0.0,
    "speed":    0.0,
    "tmp_mot":  25.0,
    "tmp_cont": 25.0,
    "tmp_cap":  25.0,
    "soc":      90.0,
    "odo":      0.0,
}

def compute_snapshot(t: float) -> dict:
    throttle = state["throttle"] / 100.0   # 0-1
    brake    = state["brake"]    / 100.0   # 0-1

    # ── RPM con inercia ────────────────────────────────────────────────────────
    target_rpm = throttle * 5000.0
    if brake > 0:
        target_rpm = max(0, target_rpm - brake * 3000)
    inertia_up   = 0.12
    inertia_down = 0.18
    inertia = inertia_up if target_rpm > veh["rpm"] else inertia_down
    veh["rpm"] += (target_rpm - veh["rpm"]) * inertia
    veh["rpm"]  = max(0.0, veh["rpm"])

    # ── Velocidad con inercia ──────────────────────────────────────────────────
    target_speed = throttle * 120.0 - brake * 80.0
    target_speed = max(0.0, target_speed)
    veh["speed"] += (target_speed - veh["speed"]) * 0.08
    veh["speed"]  = max(0.0, veh["speed"])

    # ── Odómetro ───────────────────────────────────────────────────────────────
    veh["odo"] += veh["speed"] / 3.6 * INTERVAL

    # ── Corrientes y voltajes ──────────────────────────────────────────────────
    curr_p   = throttle * 120.0 - brake * 40.0 + random.uniform(-1, 1)
    curr_rms = abs(curr_p) * 0.85
    volt_p   = 58.0 - abs(curr_p) * 0.05 + random.uniform(-0.1, 0.1)
    mot_torq = throttle * 45.0 - brake * 15.0

    # ── Freno regenerativo ─────────────────────────────────────────────────────
    regen_curr = brake * 30.0
    if brake > 0:
        veh["soc"] += regen_curr * 0.0001
    else:
        veh["soc"] -= abs(curr_p) * 0.00005
    veh["soc"] = max(5.0, min(100.0, veh["soc"]))

    # ── Temperaturas con inercia térmica ──────────────────────────────────────
    veh["tmp_mot"]  += (throttle * 40 + 25 - veh["tmp_mot"])  * 0.005
    veh["tmp_cont"] += (throttle * 30 + 25 - veh["tmp_cont"]) * 0.004
    veh["tmp_cap"]  += (throttle * 20 + 25 - veh["tmp_cap"])  * 0.003

    # ── Variables derivadas ────────────────────────────────────────────────────
    tmp_max = veh["tmp_mot"] + random.uniform(0, 2)
    tmp_min = veh["tmp_mot"] - random.uniform(2, 5)

    # ── IMU simulada ───────────────────────────────────────────────────────────
    acc_x = throttle * 0.3  - brake * 0.5  + random.uniform(-0.02, 0.02)
    acc_y = random.uniform(-0.05, 0.05)
    acc_z = 1.0 + random.uniform(-0.01, 0.01)
    gyro_x = random.uniform(-0.1, 0.1)
    gyro_y = random.uniform(-0.1, 0.1)
    gyro_z = (veh["speed"] / 120.0) * 5.0 * math.sin(t / 10) + random.uniform(-0.1, 0.1)

    # ── GPS circular ──────────────────────────────────────────────────────────
    gps_lat = 19.4978 + 0.0003 * math.sin(t / 20)
    gps_lon = -99.1269 + 0.0003 * math.cos(t / 20)

    # ── Celdas de voltaje ──────────────────────────────────────────────────────
    cell_base = 3.0 + (veh["soc"] / 100.0) * 1.2
    cells = {
        f"cell_{i}": round(cell_base + random.uniform(-0.05, 0.05), 4)
        for i in range(1, 17)
    }

    return {
        "timestamp":  datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
        "vehicle_id": "25",
        "session_id": "1",
        "data": {
            "speed_v":   round(veh["speed"], 2),
            "rpm":       round(veh["rpm"], 1),
            "mot_torq":  round(mot_torq, 2),
            "curr_rms":  round(curr_rms, 2),
            "soc":       round(veh["soc"], 1),
            "volt_p":    round(volt_p, 3),
            "curr_p":    round(curr_p, 2),
            "batt_curr": round(curr_p * 1.02, 2),
            "tmp_max":   round(tmp_max, 1),
            "tmp_min":   round(tmp_min, 1),
            "tmp_mot":   round(veh["tmp_mot"], 1),
            "tmp_cont":  round(veh["tmp_cont"], 1),
            "tmp_cap":   round(veh["tmp_cap"], 1),
            "throttle":  round(state["throttle"], 1),
            "brake":     round(state["brake"], 1),
            "odo_veh":   round(veh["odo"], 1),
            "volt_a":    round(12.4 + 0.2 * math.sin(t / 5), 3),
            "curr_a":    round(3.2  + 0.3 * random.random(), 2),
            "ksy_v":     round(5.0  + 0.05 * random.random(), 3),
            "cont_st":   1.0,
            "gps_lat":   round(gps_lat, 6),
            "gps_lon":   round(gps_lon, 6),
            "acc_x":     round(acc_x, 4),
            "acc_y":     round(acc_y, 4),
            "acc_z":     round(acc_z, 4),
            "gyro_x":    round(gyro_x, 4),
            "gyro_y":    round(gyro_y, 4),
            "gyro_z":    round(gyro_z, 4),
            "cells":     cells,
        }
    }

# ─── Loop de envío en hilo separado ──────────────────────────────────────────
def send_loop():
    t = 0.0
    while True:
        snapshot = compute_snapshot(t)
        try:
            requests.post(API_URL, json=snapshot, timeout=0.5)
        except Exception as e:
            print(f"[API] Error: {e}")
        t += INTERVAL
        time.sleep(INTERVAL)

# ─── Interfaz tkinter ─────────────────────────────────────────────────────────
def build_ui():
    root = tk.Tk()
    root.title("Fénix — Simulador")
    root.configure(bg="#0d0d0d")
    root.resizable(False, False)

    FONT_TITLE = ("Segoe UI", 11, "bold")
    FONT_VAL   = ("Segoe UI", 20, "bold")
    FONT_LABEL = ("Segoe UI", 9)
    BG         = "#0d0d0d"
    FG         = "#f0f0f0"

    tk.Label(root, text="ESCUDERÍA FÉNIX — SIMULADOR",
             font=("Segoe UI", 13, "bold"), bg=BG, fg="#ff3c00").pack(pady=(16, 4))
    tk.Label(root, text="Controla throttle y brake para simular el vehículo",
             font=FONT_LABEL, bg=BG, fg="#666").pack(pady=(0, 16))

    # ── Throttle ──────────────────────────────────────────────────────────────
    frm_t = tk.Frame(root, bg=BG)
    frm_t.pack(fill="x", padx=32, pady=8)

    tk.Label(frm_t, text="THROTTLE", font=FONT_TITLE, bg=BG, fg="#27ae60").grid(
        row=0, column=0, sticky="w")
    val_t = tk.Label(frm_t, text="0 %", font=FONT_VAL, bg=BG, fg="#27ae60", width=8)
    val_t.grid(row=0, column=2, sticky="e")

    def on_throttle(v):
        state["throttle"] = float(v)
        val_t.config(text=f"{float(v):.0f} %")

    sl_t = tk.Scale(frm_t, from_=0, to=100, orient="horizontal",
                    command=on_throttle, bg=BG, fg="#27ae60",
                    troughcolor="#1a1a1a", highlightbackground=BG,
                    activebackground="#27ae60", length=400,
                    showvalue=False, sliderlength=24)
    sl_t.grid(row=0, column=1, padx=16)

    # ── Brake ─────────────────────────────────────────────────────────────────
    frm_b = tk.Frame(root, bg=BG)
    frm_b.pack(fill="x", padx=32, pady=8)

    tk.Label(frm_b, text="BRAKE     ", font=FONT_TITLE, bg=BG, fg="#e74c3c").grid(
        row=0, column=0, sticky="w")
    val_b = tk.Label(frm_b, text="0 %", font=FONT_VAL, bg=BG, fg="#e74c3c", width=8)
    val_b.grid(row=0, column=2, sticky="e")

    def on_brake(v):
        state["brake"] = float(v)
        val_b.config(text=f"{float(v):.0f} %")

    sl_b = tk.Scale(frm_b, from_=0, to=100, orient="horizontal",
                    command=on_brake, bg=BG, fg="#e74c3c",
                    troughcolor="#1a1a1a", highlightbackground=BG,
                    activebackground="#e74c3c", length=400,
                    showvalue=False, sliderlength=24)
    sl_b.grid(row=0, column=1, padx=16)

    # ── Indicadores en vivo ───────────────────────────────────────────────────
    frm_live = tk.Frame(root, bg="#1a1a1a", bd=0)
    frm_live.pack(fill="x", padx=32, pady=16)

    stats = [
        ("RPM",      "rpm",      "#e74c3c"),
        ("Velocidad","speed",    "#3498db"),
        ("SOC",      "soc",      "#27ae60"),
        ("Tmp Motor","tmp_mot",  "#e67e22"),
    ]

    live_labels = {}
    for i, (label, key, color) in enumerate(stats):
        f = tk.Frame(frm_live, bg="#1a1a1a")
        f.grid(row=0, column=i, padx=20, pady=12)
        tk.Label(f, text=label, font=FONT_LABEL, bg="#1a1a1a", fg="#666").pack()
        lbl = tk.Label(f, text="0", font=("Segoe UI", 18, "bold"),
                       bg="#1a1a1a", fg=color)
        lbl.pack()
        live_labels[key] = lbl

    def update_labels():
        live_labels["rpm"].config(text=f"{veh['rpm']:.0f}")
        live_labels["speed"].config(text=f"{veh['speed']:.1f} km/h")
        live_labels["soc"].config(text=f"{veh['soc']:.1f} %")
        live_labels["tmp_mot"].config(text=f"{veh['tmp_mot']:.1f} °C")
        root.after(100, update_labels)

    root.after(100, update_labels)

    tk.Label(root, text="Enviando a fenix_api en localhost:8050",
             font=FONT_LABEL, bg=BG, fg="#444").pack(pady=(0, 16))

    root.mainloop()

# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    t = threading.Thread(target=send_loop, daemon=True)
    t.start()
    print("Simulador Fénix iniciado — abriendo interfaz...")
    build_ui()