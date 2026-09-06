# -*- coding: utf-8 -*-
"""Diagrama de flujo: la vuelta de referencia automatizada dentro del sistema.

Genera vuelta-referencia.png. Los nombres de modulo y de campo son los reales
del proyecto, para que el diagrama sirva de guia al implementarlo.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon, FancyArrowPatch

FONDO = "white"
AZUL = "#2f7fb5"      # lo que ya existe en el proyecto
NAR = "#ef5e20"       # lo que hay que anyadir
VERDE = "#2e8b57"     # decision
GRIS = "#8a8a8a"
ROJO = "#c0392b"      # salida de aviso

fig, ax = plt.subplots(figsize=(13.6, 16.4), dpi=110, facecolor=FONDO)
ax.set_xlim(-2, 106)
ax.set_ylim(-13, 182)
ax.axis("off")

ax.text(-1, 179, "La vuelta de referencia, automatizada",
        fontsize=20, fontweight="bold", ha="left", va="center", color="#111")
ax.text(-1, 173.5,
        "Qué pasa desde que el coche cruza meta hasta que una gráfica puede alinear dos vueltas por su posición en la pista.",
        fontsize=11.5, color="#444", ha="left", va="center")


def caja(x, y, w, h, texto, color, relleno=None, fs=9.6, negrita=False):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                                boxstyle="round,pad=0.6,rounding_size=1.6",
                                ec=color, fc=relleno or "white", lw=1.7, zorder=3))
    ax.text(x, y, texto, ha="center", va="center", fontsize=fs, zorder=4,
            color="#222", fontweight=("bold" if negrita else "normal"), linespacing=1.45)
    return (x, y, w, h)


def rombo(x, y, w, h, texto, fs=9.6):
    ax.add_patch(Polygon([(x, y + h / 2), (x + w / 2, y), (x, y - h / 2), (x - w / 2, y)],
                         closed=True, ec=VERDE, fc="#f2fbf6", lw=1.7, zorder=3))
    ax.text(x, y, texto, ha="center", va="center", fontsize=fs, zorder=4,
            color="#222", linespacing=1.4)
    return (x, y, w, h)


def flecha(a, b, etiqueta=None, color="#555", lado=None, curva=0.0):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=13,
                                 color=color, lw=1.5, zorder=2,
                                 connectionstyle="arc3,rad=%s" % curva))
    if etiqueta:
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        dx = 3.2 if lado == "der" else (-3.2 if lado == "izq" else 0)
        ax.text(mx + dx, my, etiqueta, fontsize=8.8, color=color, ha="center",
                va="center", fontweight="bold",
                bbox=dict(fc="white", ec="none", pad=1.4), zorder=5)


X = 36          # columna principal
XR = 79         # columna derecha
W = 47          # ancho de caja
ab = lambda c: (c[0], c[1] - c[3] / 2)   # borde inferior
ar = lambda c: (c[0] + c[2] / 2, c[1])   # borde derecho
al = lambda c: (c[0] - c[2] / 2, c[1])   # borde izquierdo
at = lambda c: (c[0], c[1] + c[3] / 2)   # borde superior

# ── Leyenda ────────────────────────────────────────────────────────────
for i, (c, t) in enumerate([(AZUL, "ya existe en el proyecto"),
                            (NAR, "hay que añadirlo"),
                            (VERDE, "decisión"),
                            (ROJO, "aviso al equipo")]):
    ax.add_patch(FancyBboxPatch((0 + i * 25, 166), 2.4, 2.4,
                                boxstyle="round,pad=0.3,rounding_size=0.6",
                                ec=c, fc="white", lw=1.7))
    ax.text(4.4 + i * 25, 167.2, t, fontsize=9, va="center", color="#555")

# ── Flujo ──────────────────────────────────────────────────────────────
c1 = caja(X, 158, W, 8.5,
          "El MGT manda un snapshot a 10 Hz por MQTT\n"
          "con lat, lon y velocidad", AZUL)

c2 = caja(X, 146, W, 9.5,
          "vueltas.process_lap detecta el cruce de la línea de meta\n"
          "y cierra la vuelta n con su t_vuelta y su d_vuelta", AZUL)

c3 = caja(X, 134, W, 8.5,
          "mqtt_listener guarda cada muestra en InfluxDB,\n"
          "con sus coordenadas", AZUL)

d1 = rombo(X, 119.5, W + 5, 13,
           "¿Hay ya una referencia guardada\npara esta pista?\n"
           "clave: coordenadas de la línea de meta")

# Rama SÍ, hacia la derecha
c4 = caja(XR, 119.5, 34, 12,
          "Proyectar cada muestra\nsobre la referencia y guardar s_pista.\n"
          "Vale en vivo y en histórico", NAR, relleno="#fff6f1")
c5 = caja(XR, 103, 34, 10.5,
          "Las gráficas ya pueden\nalinear vueltas y sesiones\npor posición en la pista", NAR,
          relleno="#fff6f1", negrita=True)

# Rama NO, sigue abajo
d2 = rombo(X, 103, W + 5, 12,
           "¿La sesión terminó,\no ya hay 5 vueltas cerradas?")

c6 = caja(X, 87, W, 11.5,
          "FILTRO 1 · completa\n"
          "sin fixes en (0,0) y sin huecos de más de 5 m\n"
          "entre muestras consecutivas", NAR, relleno="#fff6f1")

c7 = caja(X, 74, W, 10,
          "FILTRO 2 · cierra\n"
          "el último punto a menos de 10 m del primero", NAR, relleno="#fff6f1")

c8 = caja(X, 61, W, 11.5,
          "FILTRO 3 · típica\n"
          "longitud dentro del ±5 % de la mediana\n"
          "de las vueltas válidas de la sesión", NAR, relleno="#fff6f1")

d3 = rombo(X, 46, W + 5, 11, "¿Sobrevive alguna vuelta?")

c9 = caja(XR, 46, 34, 11,
          "Aviso: no hay vuelta apta.\nRevisar el GPS o rodar más.\n"
          "El sistema sigue sin s_pista", ROJO, relleno="#fdf3f2")

c10 = caja(X, 31, W, 11.5,
           "Elegir la de longitud MÁS CERCANA A LA MEDIANA,\n"
           "no la más rápida: la rápida corta por dentro\n"
           "y sesgaría la regla de medir", NAR, relleno="#fff6f1")

c11 = caja(X, 18, W, 10,
           "Dibujarla sobre el satélite.\nEl ingeniero la acepta o la rechaza", NAR,
           relleno="#fff6f1")

c12 = caja(X, 2.5, W, 10.5,
           "Guardar remuestreada cada metro,\nasociada a esa pista. CONGELADA:\n"
           "solo se recalcula si alguien lo pide", NAR, relleno="#fff6f1", negrita=True)

# ── Conexiones ─────────────────────────────────────────────────────────
flecha(ab(c1), at(c2))
flecha(ab(c2), at(c3))
flecha(ab(c3), at(d1))
flecha(ar(d1), al(c4), "sí", lado=None, color=AZUL)
flecha(ab(c4), at(c5), color=AZUL)
flecha(ab(d1), at(d2), "no", lado="der", color=NAR)
flecha(ab(d2), at(c6), "sí", lado="der", color=NAR)
flecha(ab(c6), at(c7))
flecha(ab(c7), at(c8))
flecha(ab(c8), at(d3))
flecha(ar(d3), al(c9), "no", color=ROJO)
flecha(ab(d3), at(c10), "sí", lado="der")
flecha(ab(c10), at(c11))
flecha(ab(c11), at(c12), "acepta", lado="der")


# "no, sigue rodando": vuelve arriba
ax.add_patch(FancyArrowPatch(al(d2), (6, 103), arrowstyle="-", color=GRIS, lw=1.4))
ax.add_patch(FancyArrowPatch((6, 103), (6, 158), arrowstyle="-", color=GRIS, lw=1.4))
ax.add_patch(FancyArrowPatch((6, 158), al(c1), arrowstyle="-|>", mutation_scale=13,
                             color=GRIS, lw=1.4))
ax.text(7.6, 130, "no: sigue rodando", fontsize=8.8, color=GRIS, rotation=90,
        ha="center", va="center", fontweight="bold")

# "rechaza": vuelve a elegir
ax.add_patch(FancyArrowPatch(ar(c11), (65, 18), arrowstyle="-", color=GRIS, lw=1.4))
ax.add_patch(FancyArrowPatch((65, 18), (65, 31), arrowstyle="-", color=GRIS, lw=1.4))
ax.add_patch(FancyArrowPatch((65, 31), ar(c10), arrowstyle="-|>", mutation_scale=13,
                             color=GRIS, lw=1.4))
ax.text(67.4, 24.5, "rechaza:\nsiguiente\ncandidata", fontsize=8.4, color=GRIS,
        ha="left", va="center", fontweight="bold")

# De la referencia guardada, de vuelta a la proyeccion
ax.add_patch(FancyArrowPatch(ar(c12), (103, c12[1]), arrowstyle="-", color=NAR, lw=1.6))
ax.add_patch(FancyArrowPatch((103, c12[1]), (103, 119.5), arrowstyle="-", color=NAR, lw=1.6))
ax.add_patch(FancyArrowPatch((103, 119.5), ar(c4), arrowstyle="-|>", mutation_scale=13,
                             color=NAR, lw=1.6))
ax.text(101.4, 66, "a partir de aquí, todas las sesiones de esa pista",
        fontsize=9, color=NAR, rotation=90, ha="center", va="center", fontweight="bold")

ax.text(-1, -10.5,
        "La referencia se guarda por PISTA, no por sesión: si cambiara cada día, el análisis histórico se correría un poco cada vez.",
        fontsize=9.5, color="#777", ha="left", va="center")

fig.savefig("vuelta-referencia.png", facecolor=FONDO, bbox_inches="tight")
print("vuelta-referencia.png")
