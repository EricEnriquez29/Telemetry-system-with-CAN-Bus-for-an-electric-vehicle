# Deploy — servicios systemd

Copia versionada de los tres archivos `.service` que corren el sistema en el
servidor. Los originales viven en `/etc/systemd/system/`; estos son la
referencia para reinstalar o migrar sin reescribirlos de memoria.

| Archivo | Qué corre | Puerto |
|---|---|---|
| `fenix_backend.service` | `fenix_backend.py` — escucha MQTT, procesa y escribe en InfluxDB | 8060 (HTTP de `/set_meta` y consultas históricas) |
| `fenix_api.service` | `fenix_api.py` con uvicorn — WebSocket del dashboard | 8050 |
| `fenix_frontend.service` | `http.server` sirviendo el dashboard | 8080 |

## Qué asumen estos archivos

- El repositorio clonado en **`/opt/fenix`**, con todo perteneciendo al usuario
  `fenix`.
- Un usuario de sistema **`fenix`** sin shell de login.
- Un entorno virtual en **`/opt/fenix/venv`** con las dependencias instaladas
  (ver el README de `../Backend/`).
- Un archivo **`/opt/fenix/software/Backend/.env`** con las credenciales,
  legible solo por `fenix`. No se versiona: la plantilla es
  `../Backend/.env.example`.

Si alguna de esas rutas cambia, hay que ajustar los `.service` en consecuencia.

## Instalación en un servidor nuevo

```bash
# 1. Usuario de sistema, sin login
useradd --system --no-create-home --shell /usr/sbin/nologin fenix

# 2. Código
git clone <url-del-repo> /opt/fenix
chown -R fenix:fenix /opt/fenix

# 3. Entorno virtual y dependencias
apt install -y python3.13-venv
runuser -u fenix -- python3 -m venv /opt/fenix/venv
runuser -u fenix -- /opt/fenix/venv/bin/pip install fastapi "uvicorn[standard]" influxdb-client paho-mqtt requests

# 4. Credenciales
cp /opt/fenix/software/Backend/.env.example /opt/fenix/software/Backend/.env
nano /opt/fenix/software/Backend/.env          # rellenar los valores
chown fenix:fenix /opt/fenix/software/Backend/.env
chmod 600 /opt/fenix/software/Backend/.env

# 5. Servicios
cp /opt/fenix/software/deploy/*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now fenix_backend fenix_api fenix_frontend
systemctl is-active fenix_backend fenix_api fenix_frontend
```

También hacen falta **mosquitto** (broker MQTT, puerto 1883, con
`allow_anonymous false` y el usuario del `.env` dado de alta con
`mosquitto_passwd`) e **InfluxDB** (puerto 8086, con un token de escritura y
lectura sobre el bucket de telemetría).

## Actualizar el código ya en marcha

```bash
runuser -u fenix -- git -C /opt/fenix pull
systemctl restart fenix_backend fenix_api
```

Dos cosas que se olvidan y cuestan caro:

- **El `pull` va como `fenix`, no como root.** Si se hace como root, los
  archivos nuevos quedan con propiedad de root y acaban mezclándose las
  pertenencias dentro de `/opt/fenix`.
- **Sin `restart`, el `pull` no surte efecto.** Python lee los archivos al
  arrancar y se queda con esa copia en memoria; cambiar el archivo en disco no
  cambia el proceso que ya está corriendo. Ya ocurrió una vez: el código nuevo
  estuvo un mes en el servidor sin ejecutarse.

El Frontend es la excepción: `http.server` lee del disco en cada petición, así
que los cambios de HTML, CSS y JS se ven recargando el navegador.

## Si se modifican estos archivos

Editar los del servidor y **copiar aquí la versión nueva** — o al revés — para
que no vuelvan a divergir. Después:

```bash
systemctl daemon-reload
systemctl restart fenix_backend fenix_api fenix_frontend
```

`daemon-reload` es obligatorio tras tocar un `.service`: sin él systemd sigue
usando la definición anterior.
