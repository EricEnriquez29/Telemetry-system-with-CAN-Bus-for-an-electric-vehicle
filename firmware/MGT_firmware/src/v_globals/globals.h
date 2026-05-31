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