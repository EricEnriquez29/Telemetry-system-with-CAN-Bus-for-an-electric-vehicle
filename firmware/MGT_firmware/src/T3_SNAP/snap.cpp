#include "snap.h"
#include "../v_globals/globals.h"
#include <WiFi.h>

// ─────────────────────────────────────────
//  RESINCRONIZACIÓN NTP
//  Cada 30 minutos T3 reconecta WiFi,
//  obtiene el tiempo real y calcula Δt
// ─────────────────────────────────────────
static int64_t  drift_step     = 0;  // corrección por ciclo
static int      drift_ciclos   = 0;  // ciclos restantes de corrección
static uint32_t t_ultimo_ntp   = 0;  // millis() de última sincronización

static void resincronizar() {
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    int intentos = 0;
    while (WiFi.status() != WL_CONNECTED && intentos < 20) {
        delay(500);
        intentos++;
    }
    if (WiFi.status() != WL_CONNECTED) {
        WiFi.disconnect(true);
        WiFi.mode(WIFI_OFF);
        return;
    }

    struct tm timeinfo;
    if (getLocalTime(&timeinfo)) {
        time_t now;
        time(&now);
        uint64_t t_ntp_nuevo = (uint64_t)now * 1000ULL - millis();

        // Calcular Δt y distribuirlo en 300 ciclos
        int64_t delta = (int64_t)t_ntp_nuevo - (int64_t)t_offset;
        drift_step   = delta / 300;
        drift_ciclos = 300;
        t_offset     = t_ntp_nuevo;
    }

    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
}

// ─────────────────────────────────────────
//  TAREA T3 — Captura de snapshots 15Hz
// ─────────────────────────────────────────
void taskSnapshot(void* pvParameters) {
    t_ultimo_ntp = millis();

    for (;;) {
        // ── Resincronización NTP cada 30 minutos ──
        if (millis() - t_ultimo_ntp >= 1800000UL) {
            t_ultimo_ntp = millis();
            resincronizar();
        }

        // ── Aplicar corrección gradual de deriva ──
        if (drift_ciclos > 0) {
            t_offset += drift_step;
            drift_ciclos--;
        }

        // ── Calcular timestamp ──
        timestamp = t_offset + millis();

        // ── Construir snapshot ──
        Snapshot s;
        s.timestamp        = timestamp;
        s.current_rms      = current_rms;
        s.speed_vehicle    = speed_vehicle;
        s.odometer_vehicle = odometer_vehicle;
        s.temp_motor       = temp_motor;
        s.temp_ctrl        = temp_ctrl;
        s.temp_capacitors  = temp_capacitors;
        s.motor_torque     = motor_torque;
        s.battery_current  = battery_current;
        s.rpm              = rpm;
        s.throttle_input   = throttle_input;
        s.brake_input      = brake_input;
        s.contactor_state  = contactor_state;
        s.keyswitch_voltage= keyswitch_voltage;
        s.voltage_pack     = voltage_pack;
        s.current_pack     = current_pack;
        s.soc              = soc;
        for (int i = 0; i < 16; i++)
            s.cell_voltage[i] = cell_voltage[i];
        s.temp_max         = temp_max;
        s.temp_min         = temp_min;
        s.gps_lat          = gps_lat;
        s.gps_lon          = gps_lon;
        s.acc_x            = acc_x;
        s.acc_y            = acc_y;
        s.acc_z            = acc_z;
        s.gyro_x           = gyro_x;
        s.gyro_y           = gyro_y;
        s.gyro_z           = gyro_z;
        s.voltage_aux      = voltage_aux;
        s.current_aux      = current_aux;

        // ── Meter al buffer ──
        if (snap_count < 200) {
            snap_buffer[snap_count] = s;
            snap_count++;
        }

        vTaskDelay(pdMS_TO_TICKS(67));
    }
}