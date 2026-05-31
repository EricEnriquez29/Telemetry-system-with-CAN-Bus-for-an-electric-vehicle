#pragma once
#include <Arduino.h>

// ─────────────────────────────────────────
//  CURTIS ACF4-A — 13 variables
// ─────────────────────────────────────────
extern float current_rms;
extern float speed_vehicle;
extern float odometer_vehicle;
extern float temp_motor;
extern float temp_ctrl;
extern float temp_capacitors;
extern float motor_torque;
extern float battery_current;
extern float rpm;
extern float throttle_input;
extern float brake_input;
extern float contactor_state;
extern float keyswitch_voltage;

// ─────────────────────────────────────────
//  BMS — 19 variables
// ─────────────────────────────────────────
extern float voltage_pack;
extern float current_pack;
extern float soc;
extern float cell_voltage[16];
extern float temp_max;
extern float temp_min;

// ─────────────────────────────────────────
//  MDV — 8 variables
// ─────────────────────────────────────────
extern float gps_lat;
extern float gps_lon;
extern float acc_x;
extern float acc_y;
extern float acc_z;
extern float gyro_x;
extern float gyro_y;
extern float gyro_z;

// ─────────────────────────────────────────
//  MCA — 2 variables
// ─────────────────────────────────────────
extern float voltage_aux;
extern float current_aux;

// ─────────────────────────────────────────
//  WIFI
// ─────────────────────────────────────────
extern const char* WIFI_SSID;
extern const char* WIFI_PASS;

// ─────────────────────────────────────────
//  TIMESTAMP
// ─────────────────────────────────────────
extern uint64_t t_offset;   // offset NTP en ms
extern uint64_t timestamp;  // timestamp actual del snapshot

// ─────────────────────────────────────────
//  SNAPSHOT
// ─────────────────────────────────────────
struct Snapshot {
    uint64_t timestamp;

    // Curtis
    float current_rms;
    float speed_vehicle;
    float odometer_vehicle;
    float temp_motor;
    float temp_ctrl;
    float temp_capacitors;
    float motor_torque;
    float battery_current;
    float rpm;
    float throttle_input;
    float brake_input;
    float contactor_state;
    float keyswitch_voltage;

    // BMS
    float voltage_pack;
    float current_pack;
    float soc;
    float cell_voltage[16];
    float temp_max;
    float temp_min;

    // MDV
    float gps_lat;
    float gps_lon;
    float acc_x;
    float acc_y;
    float acc_z;
    float gyro_x;
    float gyro_y;
    float gyro_z;

    // MCA
    float voltage_aux;
    float current_aux;
};

// ─────────────────────────────────────────
//  SNAPSHOT
// ─────────────────────────────────────────
extern Snapshot snap_buffer[200];
extern int      snap_count;

// ─────────────────────────────────────────
//  SESIÓN
// ─────────────────────────────────────────
extern int  session_ID;
extern bool sesion_activa;