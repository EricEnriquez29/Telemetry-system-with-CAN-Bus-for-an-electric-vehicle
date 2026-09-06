# -*- coding: utf-8 -*-
"""Cómo se calcula la posición en la pista. Misma geometria que demo-ploteo.html."""
import numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch

M_LAT = 111320.0
M_LON = 111320.0 * np.cos(np.radians(19.5042))


def punto(u, desv=0.0):
    """Punto de la pista en metros. desv = metros perpendicular a la trazada."""
    u = np.atleast_1d(np.asarray(u, float))
    desv = np.broadcast_to(np.atleast_1d(desv), u.shape)

    def base(uu):
        a = uu * 2 * np.pi
        rx = 0.00064 * (1 + 0.18 * np.sin(3 * a))
        ry = 0.00044 * (1 + 0.12 * np.cos(2 * a))
        return rx * np.cos(a) * M_LON, ry * np.sin(a) * M_LAT

    x, y = base(u)
    e = 1e-5
    x1, y1 = base(u - e)
    x2, y2 = base(u + e)
    dx, dy = x2 - x1, y2 - y1
    L = np.hypot(dx, dy)
    L[L == 0] = 1
    # Perpendicular a la tangente: girar (dx, dy) noventa grados, no reflejarlo
    return x - (dy / L) * desv, y + (dx / L) * desv


def trazada(amp, fase, n=4000):
    u = np.linspace(0, 1, n)
    # Siempre hacia fuera: la vuelta se abre en las curvas y nunca corta por
    # dentro, asi el error del odometro se acumula en un solo sentido.
    return punto(u, -amp * (0.5 - 0.5 * np.cos(3 * u * 2 * np.pi + fase)))


def arco(x, y):
    return np.concatenate([[0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))])


# -- Referencia: una vuelta limpia, remuestreada cada metro --------------
xr0, yr0 = trazada(0.0, 0.0)
sr0 = arco(xr0, yr0)
SR = np.arange(0, sr0[-1], 1.0)
XR = np.interp(SR, sr0, xr0)
YR = np.interp(SR, sr0, yr0)
LARGO = sr0[-1]

# -- Vuelta que se abre. Exagerada para que se vea. ----------------------
AMP = 4.0
xa, ya = trazada(AMP, 0.9)
sa = arco(xa, ya)                      # esto es el ODOMETRO de esa vuelta
sm = np.arange(0, sa[-1], 2.5)         # muestras del GPS cada ~2.5 m
XM = np.interp(sm, sa, xa)
YM = np.interp(sm, sa, ya)


# -- Proyeccion hacia adelante, ventana de 30 m -------------------------
def proyectar(xm, ym):
    j, out = 0, []
    for x, y in zip(xm, ym):
        hasta = min(len(XR) - 1, j + 30)
        k = j + int(np.argmin((XR[j:hasta + 1] - x) ** 2 + (YR[j:hasta + 1] - y) ** 2))
        j = k
        out.append(SR[k])
    return np.array(out)


S_PISTA = proyectar(XM, YM)

# Posicion REAL de cada muestra: la referencia comparte parametro u con la
# vuelta abierta, asi que se sabe exactamente en que metro de pista esta cada
# una. Sirve para medir el error de los dos metodos.
u_grid = np.linspace(0, 1, len(xa))
u_m = np.interp(sm, sa, u_grid)
S_REAL = np.interp(u_m, np.linspace(0, 1, len(sr0)), sr0)

# =======================================================================
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                     "axes.edgecolor": "#999", "text.color": "#222",
                     "axes.labelcolor": "#222",
                     "xtick.color": "#555", "ytick.color": "#555"})
fig = plt.figure(figsize=(13.6, 9.6), dpi=150, facecolor="white")
gs = fig.add_gridspec(2, 2, height_ratios=[1.18, 1], hspace=0.42, wspace=0.24,
                      left=0.065, right=0.975, top=0.845, bottom=0.085)
GRIS, NAR, AZUL = "#8a8a8a", "#ef5e20", "#2f7fb5"

fig.suptitle("Cómo se calcula la posición en la pista", x=0.065, ha="left",
             fontsize=17, fontweight="bold", y=0.975)
fig.text(0.065, 0.930,
         "Cada muestra del GPS se lleva a la trazada de referencia y hereda SU distancia. "
         "Abrirse en una curva deja de sumar metros al eje.",
         fontsize=10.5, color="#444", ha="left")

# -- (a) El circuito ----------------------------------------------------
ax = fig.add_subplot(gs[0, 0])
ax.set_aspect("equal")
ax.plot(xr0, yr0, color=GRIS, lw=2.2, label="Trazada de referencia (vuelta 1)")
ax.plot(xa, ya, color=NAR, lw=2.2, label="Otra vuelta: se abre en las curvas")
for i in range(0, len(XM), 9):
    k = int(round(S_PISTA[i]))
    ax.plot([XM[i], XR[k]], [YM[i], YR[k]], color="#cfcfcf", lw=0.8, zorder=0)
ax.scatter(XM[::9], YM[::9], s=9, color=NAR, zorder=3)
ZX, ZY, ZW, ZH = 18, 34, 34, 24
ax.add_patch(Rectangle((ZX, ZY), ZW, ZH, fill=False, ec="#111", lw=1.4, ls=(0, (4, 3))))
ax.annotate("ampliado en (b)", xy=(ZX + ZW * 0.5, ZY), xytext=(ZX - 34, ZY - 26),
            fontsize=8.8, color="#111", fontweight="bold",
            arrowprops=dict(arrowstyle="->", color="#111", lw=1.0))
ax.plot([xr0[0]], [yr0[0]], marker="s", ms=7, color="#111", zorder=5)
ax.annotate("meta" + chr(10) + "metro 0", xy=(xr0[0], yr0[0]), xytext=(xr0[0] - 2, yr0[0] + 16),
            fontsize=8.8, ha="center",
            arrowprops=dict(arrowstyle="->", color="#111", lw=0.9))
ax.set_title("(a)  El circuito y las dos trazadas", loc="left", fontsize=11, fontweight="bold")
ax.set_xlabel("metros")
ax.set_ylabel("metros")
ax.legend(loc="lower center", frameon=True, framealpha=0.93, edgecolor="none", fontsize=8.6)
ax.grid(color="#eee")

# -- (b) Zoom: la proyeccion --------------------------------------------
ax = fig.add_subplot(gs[0, 1])
ax.set_aspect("equal")
ax.plot(xr0, yr0, color=GRIS, lw=2.4)
ax.plot(xa, ya, color=NAR, lw=2.4)
mr = (XR > ZX - 16) & (XR < ZX + ZW + 16) & (YR > ZY - 16) & (YR < ZY + ZH + 16)
ax.scatter(XR[mr], YR[mr], s=7, color=GRIS, zorder=3)
sel = [i for i in range(len(XM)) if ZX <= XM[i] <= ZX + ZW and ZY <= YM[i] <= ZY + ZH]
for i in sel:
    k = int(round(S_PISTA[i]))
    ax.add_patch(FancyArrowPatch((XM[i], YM[i]), (XR[k], YR[k]), color="#666", lw=0.9,
                                 arrowstyle="-|>", mutation_scale=8, zorder=4))
ax.scatter(XM[sel], YM[sel], s=26, color=NAR, ec="white", lw=0.7, zorder=5)
if sel:
    i = sel[len(sel) // 2]
    k = int(round(S_PISTA[i]))
    ax.scatter([XM[i]], [YM[i]], s=95, color=NAR, ec="#111", lw=1.5, zorder=6)
    ax.scatter([XR[k]], [YR[k]], s=95, color="#111", zorder=6)
    ax.annotate("esta muestra…", xy=(XM[i], YM[i]), xytext=(XM[i] - 15, YM[i] + 9),
                fontsize=9, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color="#111", lw=1.1))
    ax.annotate("…hereda el metro %d\nde la referencia" % SR[k], xy=(XR[k], YR[k]),
                xytext=(XR[k] + 6, YR[k] - 13), fontsize=9, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color="#111", lw=1.1))
ax.set_xlim(ZX - 8, ZX + ZW + 18)
ax.set_ylim(ZY - 16, ZY + ZH + 13)
ax.set_title("(b)  Ampliación: el punto más cercano de la referencia",
             loc="left", fontsize=11, fontweight="bold")
ax.set_xlabel("metros")
ax.set_ylabel("metros")
ax.grid(color="#eee")
ax.text(0.985, 0.035, "la referencia va remuestreada cada metro",
        transform=ax.transAxes, ha="right", fontsize=8.2, color="#777")

# -- (c) El error de cada metodo ----------------------------------------
ax = fig.add_subplot(gs[1, 0])
err_od = sm - S_REAL
err_pi = S_PISTA - S_REAL
ax.fill_between(sm, 0, err_od, color=NAR, alpha=0.12)
ax.plot(sm, err_od, color=NAR, lw=2.2, label="Distancia recorrida (odómetro)")
ax.plot(sm, err_pi, color=AZUL, lw=2.2, label="Posición en la pista")
ax.axhline(0, color="#bbb", lw=0.9, zorder=0)
ax.set_title("(c)  Cuánto se equivoca cada eje sobre dónde está el coche",
             loc="left", fontsize=11, fontweight="bold")
ax.set_xlabel("avance por la vuelta [m]")
ax.set_ylabel("error respecto al" + chr(10) + "punto real de pista [m]")
ax.set_xlim(0, sa[-1])
lo = min(err_od.min(), err_pi.min())
hi = max(err_od.max(), err_pi.max())
pad = 0.18 * (hi - lo)
ax.set_ylim(lo - pad, hi + pad * 3.2)
ax.grid(color="#eee")
ax.legend(loc="upper right", frameon=True, framealpha=0.93, edgecolor="none", fontsize=8.6)
ax.annotate("cada metro de más se arrastra" + chr(10) + "y ya no se recupera",
            xy=(sa[-1] * 0.82, err_od[int(len(sm) * 0.82)]),
            xytext=(sa[-1] * 0.28, hi * 0.42), fontsize=9, color=NAR,
            fontweight="bold", arrowprops=dict(arrowstyle="->", color=NAR, lw=1.2))
ax.annotate("error acotado: media unidad de resolución" + chr(10) + "de la referencia, y no se acumula",
            xy=(sa[-1] * 0.60, err_pi[int(len(sm) * 0.60)]),
            xytext=(sa[-1] * 0.28, lo + (hi - lo) * 0.10), fontsize=9, color=AZUL,
            fontweight="bold", arrowprops=dict(arrowstyle="->", color=AZUL, lw=1.2))

# -- (d) La consecuencia al comparar -------------------------------------
ax = fig.add_subplot(gs[1, 1])
X = 240.0
i_od = int(np.argmin(np.abs(sm - X)))
k_od = int(round(S_PISTA[i_od]))
k_pi = int(np.argmin(np.abs(SR - X)))
err = SR[k_pi] - SR[k_od]
ax.set_aspect("equal")
ax.plot(xr0, yr0, color=GRIS, lw=2.4)
ax.plot(xa, ya, color=NAR, lw=2.4)
ax.plot(XR[k_od:k_pi + 1], YR[k_od:k_pi + 1], color="#111", lw=4.5, alpha=0.35, zorder=2)
ax.scatter([XR[k_pi]], [YR[k_pi]], s=115, color=AZUL, ec="white", lw=1.2, zorder=6)
ax.scatter([XM[i_od]], [YM[i_od]], s=115, color=NAR, ec="white", lw=1.2, zorder=6)
ax.annotate("con odómetro, X = 240 m\ncae aquí: es el metro %d real" % SR[k_od],
            xy=(XM[i_od], YM[i_od]), xytext=(XM[i_od] + 24, YM[i_od] - 14),
            fontsize=9, color=NAR, fontweight="bold", ha="left",
            arrowprops=dict(arrowstyle="->", color=NAR, lw=1.2))
ax.annotate("con posición en la pista,\nX = 240 m es este punto",
            xy=(XR[k_pi], YR[k_pi]), xytext=(XR[k_pi] + 8, YR[k_pi] + 28),
            fontsize=9, color=AZUL, fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=AZUL, lw=1.2))
ax.set_title("(d)  Al comparar en X = 240 m: %.0f m de pista de diferencia" % abs(err),
             loc="left", fontsize=11, fontweight="bold")
ax.set_xlabel("metros")
ax.set_ylabel("metros")
ax.grid(color="#eee")

fig.text(0.065, 0.022,
         "Trazada exagerada, hasta %.0f m de apertura, para que el efecto se vea en un "
         "circuito de solo %.0f m. La vuelta que se abre recorre %.1f m. "
         "Error máximo: %.1f m con odómetro, %.2f m con posición en la pista."
         % (AMP, LARGO, sa[-1], np.abs(err_od).max(), np.abs(err_pi).max()),
         fontsize=8.4, color="#777")
fig.savefig("posicion-en-pista.png", facecolor="white")
print("circuito %.1f m | vuelta abierta %.1f m" % (LARGO, sa[-1]))
print("error maximo: odometro %.1f m | posicion en pista %.1f m"
      % (np.abs(err_od).max(), np.abs(err_pi).max()))
print("en X=240 m la diferencia de punto de pista es %.1f m" % abs(err))
