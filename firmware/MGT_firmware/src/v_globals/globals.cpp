#include "globals.h"

// ─────────────────────────────────────────
//  CURTIS ACF4-A
// ─────────────────────────────────────────
float curr_rms   = -1;
float speed_v     = -1;
float odo_veh     = -1;
float tmp_mot     = -1;
float tmp_cont    = -1;
float tmp_cap     = -1;
float mot_torq    = -1;
float batt_curr   = -1;
float rpm         = -1;
float throttle    = -1;
float brake       = -1;
float cont_st     = -1;
float ksy_v       = -1;

// ─────────────────────────────────────────
//  BMS
// ─────────────────────────────────────────
float volt_p       = -1;
float curr_p       = -1;
float soc          = -1;
float cell_volts[16] = {
    -1,-1,-1,-1,-1,-1,-1,-1,
    -1,-1,-1,-1,-1,-1,-1,-1
};
float tmp_max      = -1;
float tmp_min      = -1;

// ─────────────────────────────────────────
//  MDV
// ─────────────────────────────────────────
float gps_lat  = -1;
float gps_lon  = -1;
float acc_x    = -1;
float acc_y    = -1;
float acc_z    = -1;
float gyro_x   = -1;
float gyro_y   = -1;
float gyro_z   = -1;

// ─────────────────────────────────────────
//  MCA
// ─────────────────────────────────────────
float volt_a = -1;
float curr_a = -1;

// ─────────────────────────────────────────
//  WIFI
// ─────────────────────────────────────────
const char* WIFI_SSID = "ARRIS-FED2";
const char* WIFI_PASS = "C704208B40622E42";

// ─────────────────────────────────────────
//  TIMESTAMP
// ─────────────────────────────────────────
uint64_t t_offset  = 0;
uint64_t timestamp = 0;

// ─────────────────────────────────────────
//  SNAPSHOT
// ─────────────────────────────────────────
Snapshot snap_buffer[200];
int      snap_count = 0;
// ─────────────────────────────────────────
//  SESIÓN
// ─────────────────────────────────────────
int  session_ID   = 0;
bool sesion_activa = false;

// ─────────────────────────────────────────
//  WATCHDOG
// ─────────────────────────────────────────
int counterWD = 0;

// ─────────────────────────────────────────
//  MQTT
// ─────────────────────────────────────────
SemaphoreHandle_t snap_mutex     = NULL;  // se inicializa en main.cpp
uint32_t          mqtt_publicaciones = 0;
bool              mqtt_wifi_ok    = false;
bool              mqtt_conectado  = false;
bool              mqtt_tx_on      = false;

// Mutex global para proteger variables compartidas
SemaphoreHandle_t globals_mutex = NULL;
