#pragma once
#include <Arduino.h>

// ─────────────────────────────────────────
//  CURTIS ACF4-A — 13 variables
// ─────────────────────────────────────────
extern float curr_rms;
extern float speed_v;
extern float odo_veh;
extern float tmp_mot;
extern float tmp_cont;
extern float tmp_cap;
extern float mot_torq;
extern float batt_curr;
extern float rpm;
extern float throttle;
extern float brake;
extern float cont_st;
extern float ksy_v;

// ─────────────────────────────────────────
//  BMS — 19 variables
// ─────────────────────────────────────────
extern float volt_p;
extern float curr_p;
extern float soc;
extern float cell_volts[16];
extern float tmp_max;
extern float tmp_min;

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
extern float volt_a;
extern float curr_a;

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
    float curr_rms;
    float speed_v;
    float odo_veh;
    float tmp_mot;
    float tmp_cont;
    float tmp_cap;
    float mot_torq;
    float batt_curr;
    float rpm;
    float throttle;
    float brake;
    float cont_st;
    float ksy_v;

    // BMS
    float volt_p;
    float curr_p;
    float soc;
    float cell_volts[16];
    float tmp_max;
    float tmp_min;

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
    float volt_a;
    float curr_a;
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

// ─────────────────────────────────────────
//  WATCHDOG
// ─────────────────────────────────────────
extern int counterWD;

// ─────────────────────────────────────────
//  MQTT
// ─────────────────────────────────────────
extern SemaphoreHandle_t snap_mutex;  // protege acceso al buffer entre T4 y T5
extern uint32_t mqtt_publicaciones;   // contador total de publicaciones enviadas
extern bool     mqtt_wifi_ok;         // true si WiFi está conectado
extern bool     mqtt_conectado;       // true si broker MQTT está conectado
extern bool     mqtt_tx_on;           // true si hay transmisión activa

// Mutex global para proteger variables compartidas
extern SemaphoreHandle_t globals_mutex;
