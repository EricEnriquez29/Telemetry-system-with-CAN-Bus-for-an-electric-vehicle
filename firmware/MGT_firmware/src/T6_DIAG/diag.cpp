#include "diag.h"
#include "../T1_CAN/can.h"
#include "../v_globals/globals.h"

void taskDiagnostics(void* pvParameters) {
    Serial.println("[T6] Diagnostics iniciada");

    uint32_t prev[14] = {0};
    bool status_can = true;

    for (;;) {
        uint32_t curr[14];
        can_snapshot_counts(curr);

        status_can = true;

        for (int i = 0; i < 14; i++) {
            if (curr[i] == prev[i]) {
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

        Serial.print(" snap_count: ");
        Serial.println(snap_count);

        Serial.print(" session_ID: ");
        Serial.print(session_ID);
        Serial.print(" | sesion_activa: ");
        Serial.println(sesion_activa ? "SI" : "NO");

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
        Serial.println(" Snapshot mas reciente:");

        if (snap_count > 0) {
            Snapshot& s = snap_buffer[snap_count - 1];

            uint32_t ms  = s.timestamp % 1000;
            time_t   seg = s.timestamp / 1000;
            struct tm* t = localtime(&seg);
            Serial.print(" Timestamp: ");
            Serial.print(t->tm_year + 1900); Serial.print("-");
            if (t->tm_mon + 1 < 10) Serial.print("0");
            Serial.print(t->tm_mon  + 1);    Serial.print("-");
            if (t->tm_mday < 10) Serial.print("0");
            Serial.print(t->tm_mday);        Serial.print(" ");
            if (t->tm_hour < 10) Serial.print("0");
            Serial.print(t->tm_hour);        Serial.print(":");
            if (t->tm_min < 10) Serial.print("0");
            Serial.print(t->tm_min);         Serial.print(":");
            if (t->tm_sec < 10) Serial.print("0");
            Serial.print(t->tm_sec);         Serial.print(".");
            Serial.println(ms);

            Serial.print(" Spd=");   Serial.print(s.speed_vehicle,  1);
            Serial.print(" Irms=");  Serial.print(s.current_rms,    1);
            Serial.print(" SOC=");   Serial.print(s.soc,             1);
            Serial.print(" Vpack="); Serial.print(s.voltage_pack,   1);
            Serial.print(" Lat=");   Serial.print(s.gps_lat,         6);
            Serial.print(" Lon=");   Serial.println(s.gps_lon,       6);
            Serial.print(" AccX=");  Serial.print(s.acc_x,           2);
            Serial.print(" Vaux=");  Serial.println(s.voltage_aux,  2);
        } else {
            Serial.println(" Sin snapshots aun");
        }

        Serial.println("============================================================");

        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}