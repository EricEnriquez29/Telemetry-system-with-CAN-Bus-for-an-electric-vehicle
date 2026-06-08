#include <Arduino.h>
#include <WiFi.h>
#include "v_globals/globals.h"
#include "T1_CAN/can.h"
#include "T2_PROCESSING/processing.h"
#include "T3_SNAP/snap.h"
#include "T4_MQTT/mqtt.h"
#include "T5_MICROSD/mSD.h"
#include "T6_DIAG/diag.h"

void setup() {
    Serial.begin(115200);
    Serial.println("ARRANCANDO MGT - Escuderia Fenix");

    // ── Crear mutex antes de arrancar tareas ──
    snap_mutex    = xSemaphoreCreateMutex();
    globals_mutex = xSemaphoreCreateMutex();

    // ── WiFi ──
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    Serial.print("Conectando WiFi");
    int intentos = 0;
    while (WiFi.status() != WL_CONNECTED && intentos < 40) {
        delay(500);
        Serial.print(".");
        intentos++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\nWiFi OK");

        // ── NTP — no salir hasta sincronizar ──
        configTime(-6 * 3600, 0, "pool.ntp.org", "time.google.com");
        struct tm timeinfo;
        Serial.print("Sincronizando con NTP");
        while (!getLocalTime(&timeinfo)) {
            Serial.print(".");
            delay(1000);
        }
        Serial.println("\nNTP sincronizado");

        // ── Calcular t_offset ──
        time_t now;
        time(&now);
        t_offset = (uint64_t)now * 1000ULL - millis();

        Serial.println("WiFi listo para T4");

    } else {
        Serial.println("\nWiFi no disponible");
    }

    // ── Crear tareas FreeRTOS ──
    xTaskCreatePinnedToCore(taskCAN,         "T1_CAN",  4096, NULL, 5, NULL, 0);
    xTaskCreatePinnedToCore(taskProcessing,  "T2_PROC", 4096, NULL, 4, NULL, 0);
    xTaskCreatePinnedToCore(taskSnapshot,    "T3_SNAP", 4096, NULL, 4, NULL, 0);
    xTaskCreatePinnedToCore(taskMQTT,        "T4_MQTT", 8192, NULL, 3, NULL, 0);
    xTaskCreatePinnedToCore(taskStorage,     "T5_SD",   8192, NULL, 2, NULL, 1);
    xTaskCreatePinnedToCore(taskDiagnostics, "T6_DIAG", 4096, NULL, 3, NULL, 1);
}

void loop() { vTaskDelete(NULL); }