#include "diag.h"
#include "../T1_CAN/can.h"
#include "../v_globals/globals.h"
#include "../../include/config.h"
#include <Preferences.h>
#include <esp_task_wdt.h>

// ─────────────────────────────────────────
//  FRECUENCIAS ESPERADAS POR ID
// ─────────────────────────────────────────
static const uint32_t expected[14] = {
    10, 10, 10, 1,
    10, 10, 10, 10, 10, 5,
    10, 15, 15,
    1
};

static const char* id_names[14] = {
    "0x1A7","0x2A7","0x3A7","0x4A7",
    "0x200","0x201","0x202","0x203","0x204","0x210",
    "0x400","0x401","0x402","0x500"
};

static const uint16_t id_hex[14] = {
    0x1A7, 0x2A7, 0x3A7, 0x4A7,
    0x200, 0x201, 0x202, 0x203, 0x204, 0x210,
    0x400, 0x401, 0x402, 0x500
};

// ─────────────────────────────────────────
//  ESTADISTICAS DE SESIÓN
// ─────────────────────────────────────────
static uint32_t counts_inicio[14] = {0};
static uint32_t t_sesion_inicio    = 0;

static void imprimir_estadisticas_sesion() {
    uint32_t duracion = (millis() - t_sesion_inicio) / 1000;
    if (duracion == 0) duracion = 1;

    uint32_t curr[14];
    can_snapshot_counts(curr);

    uint32_t total_recibidas = 0;
    uint32_t total_esperadas = 0;

    Serial.println("============================================================");
    Serial.println(" ESTADISTICAS CAN DE SESION");
    Serial.println("============================================================");
    Serial.print(" session_ID: ");  Serial.println(session_ID);
    Serial.print(" Duracion: ");    Serial.print(duracion); Serial.println(" s");
    Serial.print(" counterWD: ");   Serial.println(counterWD);
    Serial.println();
    Serial.println(" ID       Recibidas  Esperadas  Recepcion");
    Serial.println(" ------------------------------------------------");

    for (int i = 0; i < 14; i++) {
        uint32_t recibidas = curr[i] - counts_inicio[i];
        uint32_t esperadas = expected[i] * duracion;
        float    recepcion = esperadas > 0 ? (float)recibidas / esperadas * 100.0f : 0.0f;
        if (recepcion > 100.0f) recepcion = 100.0f;

        total_recibidas += recibidas;
        total_esperadas += esperadas;

        Serial.print(" ");
        Serial.print(id_names[i]);
        Serial.print("    ");
        Serial.print(recibidas);
        Serial.print("       ");
        Serial.print(esperadas);
        Serial.print("      ");
        Serial.print(recepcion, 2);
        Serial.println("%");
    }

    float recepcion_global = total_esperadas > 0 ?
        (float)total_recibidas / total_esperadas * 100.0f : 0.0f;
    if (recepcion_global > 100.0f) recepcion_global = 100.0f;

    Serial.println(" ------------------------------------------------");
    Serial.print(" Total recibidas : "); Serial.println(total_recibidas);
    Serial.print(" Total esperadas : "); Serial.println(total_esperadas);
    Serial.print(" Recepcion global: "); Serial.print(recepcion_global, 2); Serial.println("%");
    Serial.println("============================================================");
}

// ─────────────────────────────────────────
//  TAREA T6
// ─────────────────────────────────────────
void taskDiagnostics(void* pvParameters) {
    Serial.println("[T6] Diagnostics iniciada");

    // ── LEDs ──
    pinMode(LED_VERDE, OUTPUT);
    pinMode(LED_AZUL,  OUTPUT);
    pinMode(LED_ROJO,  OUTPUT);
    digitalWrite(LED_VERDE, LOW);
    digitalWrite(LED_AZUL,  LOW);
    digitalWrite(LED_ROJO,  LOW);

    // ── Watchdog ──
    Preferences nvs;
    nvs.begin("mgt_wd", false);

    esp_reset_reason_t motivo = esp_reset_reason();
    if (motivo == ESP_RST_TASK_WDT || motivo == ESP_RST_WDT) {
        counterWD = nvs.getInt("counterWD", 0) + 1;
        nvs.putInt("counterWD", counterWD);
        Serial.print("[T6] Reinicio por WD — counterWD = ");
        Serial.println(counterWD);
    } else {
        counterWD = nvs.getInt("counterWD", 0);
    }

    esp_task_wdt_init(10, true);
    esp_task_wdt_add(NULL);

    // ── Estado interno ──
    uint32_t prev[14]    = {0};
    bool     status_can  = true;
    bool     led_verde   = false;
    bool     led_azul    = false;
    uint32_t t_led_verde = 0;
    uint32_t t_led_azul  = 0;
    bool     prev_sesion = false;

    for (;;) {
        esp_task_wdt_reset();

        uint32_t ahora = millis();
        uint32_t curr[14];
        can_snapshot_counts(curr);

        // ── Evaluar IDs ──
        status_can = true;
        for (int i = 0; i < 14; i++) {
            uint32_t delta = curr[i] - prev[i];
            if (delta == 0) {
                status_can = false;
                switch (i) {
                    case 0:  current_rms = speed_vehicle = odometer_vehicle = -1; break;
                    case 1:  temp_motor = temp_ctrl = temp_capacitors = motor_torque = -1; break;
                    case 2:  battery_current = rpm = throttle_input = brake_input = -1; break;
                    case 3:  contactor_state = keyswitch_voltage = -1; break;
                    case 4:  voltage_pack = current_pack = soc = -1; break;
                    case 5:  cell_voltage[0] = cell_voltage[1] = cell_voltage[2] = cell_voltage[3] = -1; break;
                    case 6:  cell_voltage[4] = cell_voltage[5] = cell_voltage[6] = cell_voltage[7] = -1; break;
                    case 7:  cell_voltage[8] = cell_voltage[9] = cell_voltage[10] = cell_voltage[11] = -1; break;
                    case 8:  cell_voltage[12] = cell_voltage[13] = cell_voltage[14] = cell_voltage[15] = -1; break;
                    case 9:  temp_max = temp_min = -1; break;
                    case 10: gps_lat = gps_lon = -1; break;
                    case 11: acc_x = acc_y = acc_z = -1; break;
                    case 12: gyro_x = gyro_y = gyro_z = -1; break;
                    case 13: voltage_aux = current_aux = -1; break;
                }
            }
        }
        for (int i = 0; i < 14; i++) prev[i] = curr[i];

        // ── Detectar inicio de sesión ──
        if (sesion_activa && !prev_sesion) {
            t_sesion_inicio = ahora;
            can_snapshot_counts(counts_inicio);
        }

        // ── Detectar cierre de sesión → imprimir estadísticas ──
        if (!sesion_activa && prev_sesion) {
            imprimir_estadisticas_sesion();
        }

        prev_sesion = sesion_activa;

        // ── LEDs ──
        if (ahora - t_led_verde >= 500) {
            t_led_verde = ahora;
            led_verde   = !led_verde;
            digitalWrite(LED_VERDE, led_verde);
        }

        if (status_can) {
            if (ahora - t_led_azul >= 500) {
                t_led_azul = ahora;
                led_azul   = !led_azul;
                digitalWrite(LED_AZUL, led_azul);
            }
        } else {
            led_azul = false;
            digitalWrite(LED_AZUL, LOW);
        }

        digitalWrite(LED_ROJO, status_can ? LOW : HIGH);

        // ── RAM ──
        uint32_t ram_libre = esp_get_free_heap_size() / 1024;
        uint32_t ram_total = 520;
        uint32_t ram_pct   = ram_libre * 100 / ram_total;

        // ── Reporte serial ──
        Serial.println("============================================================");
        Serial.println(" Sistema de Telemetria - ISISA");
        Serial.println("============================================================");

        Serial.print(" counterWD: "); Serial.print(counterWD);
        Serial.print(" | statusCAN: ");
        Serial.println(status_can ? "OK" : "Fault");

        Serial.print(" RAM: ");
        Serial.print(ram_libre);
        Serial.print(" KB / ");
        Serial.print(ram_total);
        Serial.print(" KB (");
        Serial.print(ram_pct);
        Serial.println("%)");

        Serial.print(" Buffer CAN: ");
        Serial.print(can_fifo_size());
        Serial.print("/150 (");
        Serial.print(can_fifo_size() * 100 / 150);
        Serial.print("%) | Buffer Snap: ");
        Serial.print(snap_count);
        Serial.print("/200 (");
        Serial.print(snap_count * 100 / 200);
        Serial.println("%)");

        Serial.print(" Total tramas recibidas: ");
        Serial.println(can_total());

        Serial.print(" session_ID: ");
        Serial.print(session_ID);
        Serial.print(" | sesion_activa: ");
        Serial.println(sesion_activa ? "SI" : "NO");

        Serial.println("============================================================");
        Serial.println(" Snapshot mas reciente:");

        if (snap_count > 0) {
            Snapshot& s = snap_buffer[snap_count - 1];

            uint32_t   ms  = s.timestamp % 1000;
            time_t     seg = s.timestamp / 1000;
            struct tm* t   = localtime(&seg);
            Serial.print(" Timestamp: ");
            Serial.print(t->tm_year + 1900); Serial.print("-");
            if (t->tm_mon + 1 < 10) Serial.print("0");
            Serial.print(t->tm_mon  + 1); Serial.print("-");
            if (t->tm_mday < 10) Serial.print("0");
            Serial.print(t->tm_mday); Serial.print(" ");
            if (t->tm_hour < 10) Serial.print("0");
            Serial.print(t->tm_hour); Serial.print(":");
            if (t->tm_min < 10) Serial.print("0");
            Serial.print(t->tm_min); Serial.print(":");
            if (t->tm_sec < 10) Serial.print("0");
            Serial.print(t->tm_sec); Serial.print(".");
            Serial.println(ms);

            // Curtis
            Serial.print(" Spd=");  Serial.print(s.speed_vehicle,     1);
            Serial.print(" Irms="); Serial.print(s.current_rms,       1);
            Serial.print(" Odo=");  Serial.println(s.odometer_vehicle, 3);

            Serial.print(" Tmot="); Serial.print(s.temp_motor,      1);
            Serial.print(" Tctrl=");Serial.print(s.temp_ctrl,       1);
            Serial.print(" Tcap="); Serial.print(s.temp_capacitors, 1);
            Serial.print(" Trq=");  Serial.println(s.motor_torque,  1);

            Serial.print(" Ibat="); Serial.print(s.battery_current, 1);
            Serial.print(" RPM=");  Serial.print(s.rpm,             0);
            Serial.print(" Thr=");  Serial.print(s.throttle_input,  1);
            Serial.print(" Brk=");  Serial.println(s.brake_input,   1);

            Serial.print(" Cont="); Serial.print((int)s.contactor_state);
            Serial.print(" Vkey="); Serial.println(s.keyswitch_voltage, 1);

            // BMS
            Serial.print(" Vpack="); Serial.print(s.voltage_pack, 1);
            Serial.print(" Ipack="); Serial.print(s.current_pack, 1);
            Serial.print(" SOC=");   Serial.println(s.soc,         1);

            Serial.print(" C1=");  Serial.print(s.cell_voltage[0],  3);
            Serial.print(" C2=");  Serial.print(s.cell_voltage[1],  3);
            Serial.print(" C3=");  Serial.print(s.cell_voltage[2],  3);
            Serial.print(" C4=");  Serial.println(s.cell_voltage[3],3);

            Serial.print(" C5=");  Serial.print(s.cell_voltage[4],  3);
            Serial.print(" C6=");  Serial.print(s.cell_voltage[5],  3);
            Serial.print(" C7=");  Serial.print(s.cell_voltage[6],  3);
            Serial.print(" C8=");  Serial.println(s.cell_voltage[7],3);

            Serial.print(" C9=");  Serial.print(s.cell_voltage[8],   3);
            Serial.print(" C10="); Serial.print(s.cell_voltage[9],   3);
            Serial.print(" C11="); Serial.print(s.cell_voltage[10],  3);
            Serial.print(" C12="); Serial.println(s.cell_voltage[11],3);

            Serial.print(" C13="); Serial.print(s.cell_voltage[12],  3);
            Serial.print(" C14="); Serial.print(s.cell_voltage[13],  3);
            Serial.print(" C15="); Serial.print(s.cell_voltage[14],  3);
            Serial.print(" C16="); Serial.println(s.cell_voltage[15],3);

            Serial.print(" Tmax="); Serial.print((int)s.temp_max);
            Serial.print(" Tmin="); Serial.println((int)s.temp_min);

            // MDV
            Serial.print(" Lat="); Serial.print(s.gps_lat,  6);
            Serial.print(" Lon="); Serial.println(s.gps_lon, 6);

            Serial.print(" AccX=");  Serial.print(s.acc_x,   2);
            Serial.print(" AccY=");  Serial.print(s.acc_y,   2);
            Serial.print(" AccZ=");  Serial.println(s.acc_z, 2);

            Serial.print(" GyroX="); Serial.print(s.gyro_x,  2);
            Serial.print(" GyroY="); Serial.print(s.gyro_y,  2);
            Serial.print(" GyroZ="); Serial.println(s.gyro_z,2);

            // MCA
            Serial.print(" Vaux="); Serial.print(s.voltage_aux,  2);
            Serial.print(" Iaux="); Serial.println(s.current_aux,2);

        } else {
            Serial.println(" Sin snapshots aun");
        }

        Serial.println("============================================================");
        Serial.println("============================================================");
        Serial.print(" MQTT: Publicaciones="); Serial.println(mqtt_publicaciones);
        Serial.print(" MQTT Status: TxMQTT="); Serial.print(mqtt_tx_on   ? "ON" : "OFF");
        Serial.print(" | ConexionWiFi=");      Serial.println(mqtt_wifi_ok ? "ON" : "OFF");

        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}