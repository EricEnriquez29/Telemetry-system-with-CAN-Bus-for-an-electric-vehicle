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
            s.current_rms       = current_rms;
            s.speed_vehicle     = speed_vehicle;
            s.odometer_vehicle  = odometer_vehicle;
            s.temp_motor        = temp_motor;
            s.temp_ctrl         = temp_ctrl;
            s.temp_capacitors   = temp_capacitors;
            s.motor_torque      = motor_torque;
            s.battery_current   = battery_current;
            s.rpm               = rpm;
            s.throttle_input    = throttle_input;
            s.brake_input       = brake_input;
            s.contactor_state   = contactor_state;
            s.keyswitch_voltage = keyswitch_voltage;
            s.voltage_pack      = voltage_pack;
            s.current_pack      = current_pack;
            s.soc               = soc;
            for (int i = 0; i < 16; i++) s.cell_voltage[i] = cell_voltage[i];
            s.temp_max          = temp_max;
            s.temp_min          = temp_min;
            s.gps_lat           = gps_lat;
            s.gps_lon           = gps_lon;
            s.acc_x             = acc_x;
            s.acc_y             = acc_y;
            s.acc_z             = acc_z;
            s.gyro_x            = gyro_x;
            s.gyro_y            = gyro_y;
            s.gyro_z            = gyro_z;
            s.voltage_aux       = voltage_aux;
            s.current_aux       = current_aux;
            xSemaphoreGive(globals_mutex);
        } else {
            s.current_rms       = current_rms;
            s.speed_vehicle     = speed_vehicle;
            s.odometer_vehicle  = odometer_vehicle;
            s.temp_motor        = temp_motor;
            s.temp_ctrl         = temp_ctrl;
            s.temp_capacitors   = temp_capacitors;
            s.motor_torque      = motor_torque;
            s.battery_current   = battery_current;
            s.rpm               = rpm;
            s.throttle_input    = throttle_input;
            s.brake_input       = brake_input;
            s.contactor_state   = contactor_state;
            s.keyswitch_voltage = keyswitch_voltage;
            s.voltage_pack      = voltage_pack;
            s.current_pack      = current_pack;
            s.soc               = soc;
            for (int i = 0; i < 16; i++) s.cell_voltage[i] = cell_voltage[i];
            s.temp_max          = temp_max;
            s.temp_min          = temp_min;
            s.gps_lat           = gps_lat;
            s.gps_lon           = gps_lon;
            s.acc_x             = acc_x;
            s.acc_y             = acc_y;
            s.acc_z             = acc_z;
            s.gyro_x            = gyro_x;
            s.gyro_y            = gyro_y;
            s.gyro_z            = gyro_z;
            s.voltage_aux       = voltage_aux;
            s.current_aux       = current_aux;
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