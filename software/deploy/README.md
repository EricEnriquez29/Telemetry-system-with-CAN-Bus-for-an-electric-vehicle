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

Hay **dos copias** de cada `.service`: la de este repo y la de
`/etc/systemd/system/` en el servidor. Systemd solo lee la segunda; esta es el
respaldo. Cambiar una sin la otra deja el respaldo mintiendo, que es peor que
no tenerlo.

`daemon-reload` es obligatorio siempre que cambie un `.service`: sin él systemd
sigue usando la definición anterior aunque el archivo en disco ya sea otro.

### Camino recomendado: editar aquí, no en el servidor

Así el repo manda siempre y no hay que sincronizar hacia atrás.

```bash
# en tu PC: editar el .service, luego
git add software/deploy && git commit && git push

# en el servidor
runuser -u fenix -- git -C /opt/fenix pull
cp /opt/fenix/software/deploy/*.service /etc/systemd/system/
systemctl daemon-reload
systemctl restart fenix_backend fenix_api fenix_frontend
systemctl is-active fenix_backend fenix_api fenix_frontend
```

### Si se editó directamente en el servidor

El servidor **puede bajar pero no subir**: su remoto no tiene credenciales, y
así debe seguir — es una máquina expuesta a internet, y un token de escritura
ahí es un riesgo que no compensa por tres archivos que cambian dos veces al
año. El cambio hay que llevarlo a mano hasta la PC de trabajo.

```bash
# en el servidor: llevar la versión viva a la carpeta del repo
cp /etc/systemd/system/fenix_*.service /opt/fenix/software/deploy/
chown fenix:fenix /opt/fenix/software/deploy/*.service

# ver qué cambió respecto a lo versionado
runuser -u fenix -- git -C /opt/fenix diff -- software/deploy/
```

Ese diff se replica en la PC de trabajo, se commitea y se sube. Después, en el
servidor, `runuser -u fenix -- git -C /opt/fenix pull` deja la copia local
limpia y alineada con el repo.

Nota: los comandos de git en el servidor van con `runuser -u fenix`. Como root
fallan con *dubious ownership*, porque el repositorio pertenece a `fenix`. Es
una protección de git — no desactivarla con `safe.directory`; ejecutar como el
usuario correcto.
