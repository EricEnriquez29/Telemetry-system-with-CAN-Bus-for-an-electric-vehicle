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