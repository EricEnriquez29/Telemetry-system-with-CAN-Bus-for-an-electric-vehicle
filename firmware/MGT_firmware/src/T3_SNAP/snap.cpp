#include "snap.h"
#include "../v_globals/globals.h"

void taskSnapshot(void* pvParameters) {

    // ── Esperar a que NTP sincronice ──
    while (t_offset == 0) {
        vTaskDelay(pdMS_TO_TICKS(100));
    }

    for (;;) {
        // ── Calcular timestamp ──
        timestamp = t_offset + millis();

        // ── Construir snapshot (lectura protegida) ──
        Snapshot s;
        s.timestamp = timestamp;
        if (globals_mutex != NULL && xSemaphoreTake(globals_mutex, pdMS_TO_TICKS(10)) == pdTRUE) {
            s.curr_rms  = curr_rms;
            s.speed_v   = speed_v;
            s.odo_veh   = odo_veh;
            s.tmp_mot   = tmp_mot;
            s.tmp_cont  = tmp_cont;
            s.tmp_cap   = tmp_cap;
            s.mot_torq  = mot_torq;
            s.batt_curr = batt_curr;
            s.rpm       = rpm;
            s.throttle  = throttle;
            s.brake     = brake;
            s.cont_st   = cont_st;
            s.ksy_v     = ksy_v;
            s.volt_p    = volt_p;
            s.curr_p    = curr_p;
            s.soc       = soc;
            for (int i = 0; i < 16; i++) s.cell_volts[i] = cell_volts[i];
            s.tmp_max   = tmp_max;
            s.tmp_min   = tmp_min;
            s.gps_lat   = gps_lat;
            s.gps_lon   = gps_lon;
            s.acc_x     = acc_x;
            s.acc_y     = acc_y;
            s.acc_z     = acc_z;
            s.gyro_x    = gyro_x;
            s.gyro_y    = gyro_y;
            s.gyro_z    = gyro_z;
            s.volt_a    = volt_a;
            s.curr_a    = curr_a;
            xSemaphoreGive(globals_mutex);
        } else {
            s.curr_rms  = curr_rms;
            s.speed_v   = speed_v;
            s.odo_veh   = odo_veh;
            s.tmp_mot   = tmp_mot;
            s.tmp_cont  = tmp_cont;
            s.tmp_cap   = tmp_cap;
            s.mot_torq  = mot_torq;
            s.batt_curr = batt_curr;
            s.rpm       = rpm;
            s.throttle  = throttle;
            s.brake     = brake;
            s.cont_st   = cont_st;
            s.ksy_v     = ksy_v;
            s.volt_p    = volt_p;
            s.curr_p    = curr_p;
            s.soc       = soc;
            for (int i = 0; i < 16; i++) s.cell_volts[i] = cell_volts[i];
            s.tmp_max   = tmp_max;
            s.tmp_min   = tmp_min;
            s.gps_lat   = gps_lat;
            s.gps_lon   = gps_lon;
            s.acc_x     = acc_x;
            s.acc_y     = acc_y;
            s.acc_z     = acc_z;
            s.gyro_x    = gyro_x;
            s.gyro_y    = gyro_y;
            s.gyro_z    = gyro_z;
            s.volt_a    = volt_a;
            s.curr_a    = curr_a;
        }

        // ── Meter al buffer (protegido) ──
        if (snap_mutex != NULL) {
            if (xSemaphoreTake(snap_mutex, pdMS_TO_TICKS(10)) == pdTRUE) {
                if (snap_count < 200) {
                    snap_buffer[snap_count] = s;
                    snap_count++;
                }
                xSemaphoreGive(snap_mutex);
            }
        } else {
            if (snap_count < 200) {
                snap_buffer[snap_count] = s;
                snap_count++;
            }
        }

        vTaskDelay(pdMS_TO_TICKS(67));
    }
}
