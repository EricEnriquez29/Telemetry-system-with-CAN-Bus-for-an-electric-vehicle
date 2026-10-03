# MGT compacto

Variante del firmware del MGT para un kart con **un solo ESP32**. El MGT de
siempre convive con otros dos módulos —el MDV, que lleva GPS e IMU, y el MCA,
que mide el consumo auxiliar— y recibe sus datos por CAN. Aquí no hay MDV ni
MCA: el GPS y el acelerómetro van colgados del propio MGT, y el consumo
auxiliar no se mide.

> **Estado: solo documentación.** Esta carpeta todavía no tiene código. Es el
> plan acordado, escrito antes de empezar para que lo que se programe después
> no se invente nada.

El firmware de tres módulos sigue entero en `../MGT_firmware/`. Esta variante
no lo reemplaza ni lo modifica.

## Qué cambia respecto a `MGT_firmware`

| | MGT_firmware | MGT compacto |
|---|---|---|
| Módulos | MGT + MDV + MCA | solo MGT |
| CAN que escucha | Curtis, BMS, MDV, MCA | **Curtis y BMS** |
| GPS | por CAN, desde el MDV (`0x400`) | **L76K propio, por UART** |
| Acelerómetro y giroscopio | por CAN, desde el MDV (`0x401`, `0x402`) | **MPU6050 propio, por I²C** |
| Consumo auxiliar | por CAN, desde el MCA (`0x500`) | **no se mide** |
| microSD | respaldo local por SPI | **no lleva** |

### Tramas CAN que deja de escuchar

`0x400` (GPS del MDV), `0x401` (aceleración), `0x402` (giroscopio) y `0x500`
(voltaje y corriente auxiliares del MCA). Las tablas `CAN_FREQ_NOMINAL` y
`CAN_ID_NAMES` bajan de 14 a 10 entradas; si no, el diagnóstico reporta como
caídos cuatro IDs que en este kart no existen.

### Fuera la microSD

Se quita entera: la tarea `T5_MICROSD`, sus pines y el bus SPI. Con ella se va
el segundo significado del LED rojo, que hoy parpadea cuando lo único que falla
es la tarjeta. Aquí el rojo tiene un solo significado: fijo si falla el CAN.

### El JSON que se publica

**No lleva `volt_a` ni `curr_a`.** El servidor no se toca: ya los lee con
`data.get("volt_a", 0)` y el tablero con `num()`, así que al faltar valen cero y
no se cae nada. Se comprobó recorriendo los seis puntos del Backend y el único
del Frontend que los usan, y ejecutando el tramo del cálculo auxiliar con un
snapshot sin esos campos: sale todo en cero, sin excepciones, y `soc_aux` se
queda en `None`, que es lo correcto porque nunca llegan las cuatro muestras de
calibración.

La consecuencia, asumida a propósito: en este kart InfluxDB guarda ceros de
consumo auxiliar, y no hay forma de distinguirlos de un consumo real de cero.
El equipo decidió no tocar el servidor por esto.

## Pines

El ESP32 es un **WROOM**. Los pines 21 y 22, que son los de I²C por defecto,
están ocupados por el CAN, así que el MPU6050 **tiene que arrancar con
`Wire.begin(SDA, SCL)` explícito**. Conectarlo "donde va" y esperar que
responda es el error que cuesta una tarde.

| Pin | Función | Nota |
|---|---|---|
| 21 / 22 | CAN TX / RX | igual que hoy |
| 17 | TX2 → RX del L76K | `Serial2` nativo |
| 16 | RX2 ← TX del L76K | `Serial2` nativo |
| 19 | SDA del MPU6050 | pin que liberó la microSD |
| 18 | SCL del MPU6050 | pin que liberó la microSD |
| 14 | LED verde — RUN | igual que hoy |
| 27 | LED azul — CAN | igual que hoy |
| 26 | LED rojo — error de CAN | ya no indica fallo de tarjeta |
| 25 | LED amarillo — MQTT | igual que hoy |
| 1 / 3 | consola USB, 115200 | igual que hoy |

Quedan libres el 23 y el 5, que también eran de la microSD. El 5 conviene
dejarlo en paz: es pin de arranque y colgarle un sensor puede impedir que el
ESP32 arranque.

El TX al L76K (pin 17) hay que cablearlo aunque solo se reciba: es por donde se
le configura el ritmo y la velocidad del puerto.

## Frecuencias

Las mismas que hoy, para que los datos no cambien de carácter al cambiar de
kart:

| Dato | Hoy, por CAN | Aquí |
|---|---|---|
| GPS | 10 Hz (`0x400`) | 10 Hz |
| Acelerómetro | 15 Hz (`0x401`) | 15 Hz |
| Giroscopio | 15 Hz (`0x402`) | 15 Hz |

El snapshot se arma cada 67 ms, o sea a unos 15 Hz, así que muestrear el
MPU6050 a 15 Hz es justo lo que el snapshot puede aprovechar. Más rápido no
añadiría nada aguas abajo.

### El L76K no da 10 Hz de fábrica

Arranca a **1 Hz y 9600 baudios**, y hay que configurarlo al encender. A 9600
baudios caben unos 960 caracteres por segundo, y una ráfaga NMEA completa son
entre 300 y 500 bytes: a 10 Hz hacen falta del orden de 3000 a 5000 bytes por
segundo. **No cabe.** Así que la configuración de arranque tiene que hacer dos
cosas, no una:

1. Subir el puerto a 115200 baudios.
2. Apagar las sentencias que no se usan y dejar solo las necesarias.

Y después pedir los 10 Hz. Si se pide el ritmo sin tocar lo demás, llegan
tramas cortadas.

## Pendiente de decidir

- **PPS del L76K.** Si se saca, el pin reservado es el 35. No hace falta para
  que esto funcione; sirve para sincronizar el reloj con precisión.
- **INT del MPU6050.** Mismo caso: no es necesario si se lee por tiempo.
