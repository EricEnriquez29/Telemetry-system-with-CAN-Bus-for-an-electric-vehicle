import math

# ─── Constantes ───────────────────────────────────────────────────────────────
KT      = 0.143
E_NOM   = 5210.0
Q_NOM   = 100.0
I_MIN   = 10.0
N_REPOSO = 100

# ─── Snapshot de prueba ───────────────────────────────────────────────────────
data = {
    "curr_rms":  80.0,    # A
    "rpm":       3000.0,  # rpm
    "volt_p":    56.8,    # V
    "curr_p":   60.0,    # A  (negativo = consumo)
    "soc":       85.0,    # %
    "cell_volts": [3.55] * 16,
}

curr_rms   = data["curr_rms"]
rpm        = data["rpm"]
volt_p     = data["volt_p"]
curr_p     = data["curr_p"]
soc        = data["soc"]
cell_volts = data["cell_volts"]

# ── 1. Torque estimado ─────────────────────────────────────────────────────
tau_est = KT * abs(curr_rms)
print(f"τ_est  = {KT} × {curr_rms} = {tau_est:.4f} Nm")

# ── 2. Potencia mecánica ───────────────────────────────────────────────────
omega = 2 * math.pi * abs(rpm) / 60.0
p_mec = tau_est * omega
print(f"ω      = 2π × {rpm} / 60 = {omega:.4f} rad/s")
print(f"P_mec  = {tau_est:.4f} × {omega:.4f} = {p_mec:.4f} W")

# ── 3. Potencia eléctrica HV ───────────────────────────────────────────────
p_hv = volt_p * curr_p
print(f"P_HV   = {volt_p} × {curr_p} = {p_hv:.4f} W")

# ── 4. Potencia regenerativa ───────────────────────────────────────────────
if curr_p > 0:
    p_regen = volt_p * abs(curr_p)
else:
    p_regen = 0.0
print(f"P_regen= {p_regen:.4f} W  (curr_p={'positivo' if curr_p > 0 else 'negativo → 0'})")

# ── 5. Eficiencia ──────────────────────────────────────────────────────────
if abs(p_hv) > 300.0 and curr_p < 0:
    eta = (p_mec / abs(p_hv)) * 100.0
    eta = min(eta, 100.0)
else:
    eta = None
print(f"η_sist = {eta} %  (válida solo si P_HV>300W y curr_p>0)")

# ── 6-8. Acumulativas con Δt = 0.1s ───────────────────────────────────────
dt = 0.1
e_hv    = (p_hv * dt) / 3600.0
q_hv    = (curr_p * dt) / 3600.0
e_regen = (p_regen * dt) / 3600.0 if curr_p > 0 else 0.0
print(f"ΔE_HV  = {p_hv:.4f} × {dt} / 3600 = {e_hv:.8f} Wh")
print(f"ΔQ_HV  = {curr_p} × {dt} / 3600 = {q_hv:.8f} Ah")
print(f"ΔE_reg = {e_regen:.8f} Wh")

# ── 9. Capacidad restante ──────────────────────────────────────────────────
q_hv_rest = Q_NOM * soc / 100.0
print(f"Q_rest = 100 × {soc} / 100 = {q_hv_rest:.4f} Ah")

# ── 10. Energía restante ───────────────────────────────────────────────────
e_hv_rest = E_NOM * soc / 100.0
print(f"E_rest = 5210 × {soc} / 100 = {e_hv_rest:.4f} Wh")

# ── 11-12. Resistencia interna ─────────────────────────────────────────────
# Simular que V_rest se estableció antes
v_rest_pack = 57.5  # V medido en reposo anteriormente
if abs(curr_p) > I_MIN and v_rest_pack is not None:
    r_pack = (v_rest_pack - volt_p) / abs(curr_p)
    print(f"R_pack = ({v_rest_pack} - {volt_p}) / {abs(curr_p)} = {r_pack:.6f} Ω")
else:
    print(f"R_pack = None (|curr_p|={abs(curr_p)} < I_MIN={I_MIN})")

# ── 13. Resistencia por celda ──────────────────────────────────────────────
v_rest_celda = 3.59  # V en reposo
for i in range(3):  # solo primeras 3 para no llenar la pantalla
    r_cell = (v_rest_celda - cell_volts[i]) / abs(curr_p)
    print(f"R_cell_{i+1} = ({v_rest_celda} - {cell_volts[i]}) / {abs(curr_p)} = {r_cell:.8f} Ω")
print("...")