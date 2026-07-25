"""
fenix_backend.py – Escudería Fénix

Punto de entrada. Toda la lógica vive en el paquete backend_core/ (ver
backend_core/README.md para el detalle de cada módulo):
  - Escucha MQTT y guarda en InfluxDB
  - Calcula variables derivadas del tren motriz
  - Calcula orientación (Roll/Pitch) y aceleraciones compensadas (dinámica vehicular)
  - Empuja cada snapshot a fenix_api via HTTP POST (RAM)
  - Watchdog: si no llegan datos MQTT en 5s, envía snapshot con todo en cero
  - Sirve /set_meta, /session_summary y /sessions_for_date en el puerto 8060

Uso:
    pip install -r requirements.txt   (ver software/Backend/README.md)
    python fenix_backend.py
"""

from backend_core.mqtt_listener import main

if __name__ == "__main__":
    main()
