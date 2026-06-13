#include "globals.h"

// ─────────────────────────────────────────
//  CURTIS ACF4-A
// ─────────────────────────────────────────
float current_rms      = -1;
float speed_vehicle    = -1;
float odometer_vehicle = -1;
float temp_motor       = -1;
float temp_ctrl        = -1;
float temp_capacitors  = -1;
float motor_torque     = -1;
float battery_current  = -1;
float rpm              = -1;
float throttle_input   = -1;
float brake_input      = -1;
float contactor_state  = -1;
float keyswitch_voltage= -1;

// ─────────────────────────────────────────
//  BMS
// ─────────────────────────────────────────
float voltage_pack     = -1;
float current_pack     = -1;
float soc              = -1;
float cell_voltage[16] = {
    -1,-1,-1,-1,-1,-1,-1,-1,
    -1,-1,-1,-1,-1,-1,-1,-1
};
float temp_max         = -1;
float temp_min         = -1;

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
float voltage_aux = -1;
float current_aux = -1;

// ─────────────────────────────────────────
//  WIFI
// ─────────────────────────────────────────
const char* WIFI_SSID = "INFINITUMA0AA_2.4";
const char* WIFI_PASS = "hd5319GRBe";

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