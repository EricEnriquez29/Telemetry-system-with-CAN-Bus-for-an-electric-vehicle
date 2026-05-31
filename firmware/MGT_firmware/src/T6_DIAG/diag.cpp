#include "diag.h"
#include "../T1_CAN/can.h"

void taskDiagnostics(void* pvParameters) {
    Serial.println("[T6] Diagnostics iniciada");

    uint32_t prev[14] = {0};  // contadores del segundo anterior
    bool     status_can = true;

    for (;;) {
        // ── Snapshot de contadores actuales ──
        uint32_t curr[14];
        can_snapshot_counts(curr);

        // ── Evaluar si algún ID dejó de transmitir ──
        status_can = true;
        for (int i = 0; i < 14; i++) {
            if (curr[i] == prev[i]) {
                status_can = false;  // este ID no llegó en el último segundo
                break;
            }
        }

        // ── Si Fault, reintentar TWAI ──
        if (!status_can) {
            twai_stop();
            twai_start();
        }

        // ── Guardar para el siguiente segundo ──
        for (int i = 0; i < 14; i++) prev[i] = curr[i];

        // ── Imprimir reporte ──
        Serial.println("============================================================");
        Serial.println(" Sistema de Telemetria - ISISA");
        Serial.println("============================================================");

        Serial.print(" counterWD: 0 | statusCAN: ");
        Serial.println(status_can ? "OK" : "Fault");

        Serial.print(" RAM: ");
        Serial.print(esp_get_free_heap_size() / 1024);
        Serial.println(" KB Libre");

        Serial.print(" Buffer CAN: ");
        Serial.print(can_fifo_size());
        Serial.print("/150 (");
        Serial.print(can_fifo_size() * 100 / 150);
        Serial.println("%)");

        Serial.print(" Total tramas recibidas: ");
        Serial.println(can_total());

        Serial.println("============================================================");
        Serial.println(" Stats por ID:");

        Serial.print("  0x1A7:"); Serial.print(can_count(0x1A7));
        Serial.print("  0x2A7:"); Serial.print(can_count(0x2A7));
        Serial.print("  0x3A7:"); Serial.println(can_count(0x3A7));

        Serial.print("  0x4A7:"); Serial.print(can_count(0x4A7));
        Serial.print("  0x200:"); Serial.print(can_count(0x200));
        Serial.print("  0x201:"); Serial.println(can_count(0x201));

        Serial.print("  0x202:"); Serial.print(can_count(0x202));
        Serial.print("  0x203:"); Serial.print(can_count(0x203));
        Serial.print("  0x204:"); Serial.println(can_count(0x204));

        Serial.print("  0x210:"); Serial.print(can_count(0x210));
        Serial.print("  0x400:"); Serial.print(can_count(0x400));
        Serial.print("  0x401:"); Serial.println(can_count(0x401));

        Serial.print("  0x402:"); Serial.print(can_count(0x402));
        Serial.print("  0x500:"); Serial.println(can_count(0x500));

        Serial.println("============================================================");

        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}