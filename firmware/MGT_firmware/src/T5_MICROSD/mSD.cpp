#include "mSD.h"
#include "../v_globals/globals.h"
#include "../T1_CAN/can.h"
#include <Preferences.h>
#include <WiFi.h>

Preferences nvs;

// ─────────────────────────────────────────
//  CORRECCIÓN DE DERIVA NTP
// ─────────────────────────────────────────
static int64_t  drift_step   = 0;
static int      drift_ciclos = 0;
static uint32_t t_ultimo_ntp = 0;

static void resincronizar_ntp() {
    // T4 ya tiene WiFi activo — solo resincronizamos tiempo
    struct tm timeinfo;
    if (getLocalTime(&timeinfo)) {
        time_t now;
        time(&now);
        uint64_t t_ntp_nuevo = (uint64_t)now * 1000ULL - millis();
        int64_t  delta       = (int64_t)t_ntp_nuevo - (int64_t)t_offset;
        drift_step   = delta / 300;
        drift_ciclos = 300;
        t_offset     = t_ntp_nuevo;
        Serial.println("[T5] NTP resincronizado");
    }
}

// ─────────────────────────────────────────
//  LEER session_ID DE NVS AL ARRANCAR
// ─────────────────────────────────────────
static void nvs_init() {
    nvs.begin("mgt", false);

    // Esperar a que t_offset esté disponible
    uint32_t t_espera = millis();
    while (t_offset == 0) {
        if (millis() - t_espera > 10000) {
            Serial.println("[T5] NTP no disponible — session_ID sin cambios");
            session_ID = nvs.getInt("session_id", 0);
            return;
        }
        vTaskDelay(pdMS_TO_TICKS(100));
    }

    String fecha_nvs = nvs.getString("fecha", "");

    time_t now = (time_t)(t_offset / 1000);
    struct tm t;
    localtime_r(&now, &t);
    char fecha_hoy[11];
    snprintf(fecha_hoy, sizeof(fecha_hoy), "%04d-%02d-%02d",
             t.tm_year + 1900, t.tm_mon + 1, t.tm_mday);

    if (fecha_nvs == "") {
        nvs.putString("fecha", fecha_hoy);
        nvs.putInt("session_id", 0);
        session_ID = 0;
        Serial.println("[T5] Primera ejecucion — session_ID = 0");

    } else if (fecha_nvs != fecha_hoy) {
        nvs.putString("fecha", fecha_hoy);
        nvs.putInt("session_id", 0);
        session_ID = 0;
        Serial.print("[T5] Nuevo dia — session_ID reseteado a 0");
        Serial.print(" (anterior: "); Serial.print(fecha_nvs); Serial.println(")");

    } else {
        session_ID = nvs.getInt("session_id", 0);
        Serial.print("[T5] Mismo dia — session_ID = ");
        Serial.println(session_ID);
    }
}

// ─────────────────────────────────────────
//  TAREA T5
// ─────────────────────────────────────────
void taskStorage(void* pvParameters) {
    nvs_init();
    t_ultimo_ntp = millis();

    uint32_t t_inicio_actividad = 0;
    uint32_t t_ultima_trama     = 0;
    uint32_t total_anterior     = 0;
    bool     hay_actividad      = false;

    for (;;) {
        uint32_t total_actual = can_total();
        uint32_t ahora        = millis();

        // ── Resincronización NTP cada 30 minutos ──
        if (ahora - t_ultimo_ntp >= 1800000UL) {
            t_ultimo_ntp = ahora;
            resincronizar_ntp();
        }

        // ── Aplicar corrección gradual de deriva ──
        if (drift_ciclos > 0) {
            t_offset += drift_step;
            drift_ciclos--;
        }

        // ── Detectar actividad CAN ──
        if (total_actual > total_anterior) {
            total_anterior = total_actual;

            if (!hay_actividad) {
                t_inicio_actividad = ahora;
                hay_actividad      = true;
            }
            t_ultima_trama = ahora;

            // ── ¿5s continuos de tramas? → nueva sesión ──
            if (!sesion_activa && t_offset > 0 &&
                (ahora - t_inicio_actividad >= 5000)) {
                session_ID++;
                nvs.putInt("session_id", session_ID);

                time_t now = (time_t)(t_offset / 1000);
                struct tm t;
                localtime_r(&now, &t);
                char fecha_hoy[11];
                snprintf(fecha_hoy, sizeof(fecha_hoy), "%04d-%02d-%02d",
                         t.tm_year + 1900, t.tm_mon + 1, t.tm_mday);
                nvs.putString("fecha", fecha_hoy);

                counterWD = 0;
                Preferences nvs_wd;
                nvs_wd.begin("mgt_wd", false);
                nvs_wd.putInt("counterWD", 0);
                nvs_wd.end();

                sesion_activa = true;
                Serial.print("[T5] Nueva sesion — session_ID = ");
                Serial.println(session_ID);
            }

        } else {
            // ── ¿10s sin tramas? → cerrar sesión ──
            if (sesion_activa && hay_actividad &&
                (ahora - t_ultima_trama >= 10000)) {
                sesion_activa  = false;
                hay_actividad  = false;
                Serial.print("[T5] Sesion cerrada — session_ID = ");
                Serial.println(session_ID);
            }

            if (!sesion_activa && hay_actividad &&
                (ahora - t_ultima_trama >= 10000)) {
                hay_actividad = false;
            }
        }

        // ── Consumir buffer cuando llega a 200 ──
        if (snap_count >= 200) {
            if (xSemaphoreTake(snap_mutex, pdMS_TO_TICKS(10)) == pdTRUE) {
                memmove(snap_buffer, snap_buffer + 150, 50 * sizeof(Snapshot));
                snap_count = 50;
                xSemaphoreGive(snap_mutex);
            }
        }

        vTaskDelay(pdMS_TO_TICKS(100));
    }
}