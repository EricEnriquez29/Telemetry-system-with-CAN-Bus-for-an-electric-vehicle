#include <Arduino.h>
#include "T1_CAN/can.h"
#include "T2_PROCESSING/processing.h"
#include "T6_DIAG/diag.h"

void taskSnapshot   (void* pvParameters);
void taskMQTT       (void* pvParameters);
void taskStorage    (void* pvParameters);

void setup() {
    Serial.begin(115200);
    Serial.println("ARRANCANDO MGT - Escuderia Fenix");

    xTaskCreatePinnedToCore(taskCAN,         "T1_CAN",  4096, NULL, 5, NULL, 0);
    xTaskCreatePinnedToCore(taskProcessing,  "T2_PROC", 4096, NULL, 4, NULL, 0);
    xTaskCreatePinnedToCore(taskSnapshot,    "T3_SNAP", 4096, NULL, 4, NULL, 0);
    xTaskCreatePinnedToCore(taskMQTT,        "T4_MQTT", 8192, NULL, 3, NULL, 0);
    xTaskCreatePinnedToCore(taskStorage,     "T5_SD",   8192, NULL, 2, NULL, 1);
    xTaskCreatePinnedToCore(taskDiagnostics, "T6_DIAG", 4096, NULL, 3, NULL, 1);
}

void loop() { vTaskDelete(NULL); }

void taskSnapshot (void* pvParameters) { for(;;) vTaskDelay(pdMS_TO_TICKS(67));    }
void taskMQTT     (void* pvParameters) { for(;;) vTaskDelay(pdMS_TO_TICKS(100));   }
void taskStorage  (void* pvParameters) { for(;;) vTaskDelay(pdMS_TO_TICKS(10000)); }