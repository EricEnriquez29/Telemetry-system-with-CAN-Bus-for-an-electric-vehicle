#include "processing.h"
#include "../v_globals/globals.h"
#include "../T1_CAN/can.h"

// ─────────────────────────────────────────
//  HELPERS DE DECODIFICACIÓN
// ─────────────────────────────────────────

// Little Endian int16 — bytes LSB primero
// ejemplo: d[0]=C8 d[1]=01 → 0x01C8 = 456
static int16_t le16(uint8_t* d, int i) {
    return (int16_t)(d[i] | d[i+1] << 8);
}

// Little Endian int32 — bytes LSB primero
static int32_t le32(uint8_t* d, int i) {
    return (int32_t)(d[i] | d[i+1]<<8 | d[i+2]<<16 | d[i+3]<<24);
}

// Big Endian uint16 — bytes MSB primero
// ejemplo: d[0]=02 d[1]=0E → 0x020E = 526
static uint16_t be16(uint8_t* d, int i) {
    return (uint16_t)(d[i]<<8 | d[i+1]);
}

// ─────────────────────────────────────────
//  DECODIFICADORES POR ID
// ─────────────────────────────────────────

// Curtis TPDO1 — 0x1A7
// Bytes 0-1: current_rms    LE ×10
// Bytes 2-3: speed_vehicle  LE ×10
// Bytes 4-7: odometer       LE ×10
static void decode_1A7(uint8_t* d) {
    current_rms      = le16(d, 0) / 10.0f;
    speed_vehicle    = le16(d, 2) / 10.0f;
    odometer_vehicle = le32(d, 4) / 10.0f;
}

// Curtis TPDO2 — 0x2A7
// Bytes 0-1: temp_motor      LE ×10
// Bytes 2-3: temp_ctrl       LE ×10
// Bytes 4-5: temp_capacitors LE ×10
// Bytes 6-7: motor_torque    LE ×10
static void decode_2A7(uint8_t* d) {
    temp_motor      = le16(d, 0) / 10.0f;
    temp_ctrl       = le16(d, 2) / 10.0f;
    temp_capacitors = le16(d, 4) / 10.0f;
    motor_torque    = le16(d, 6) / 10.0f;
}

// Curtis TPDO3 — 0x3A7
// Bytes 0-1: battery_current LE ×10
// Bytes 2-3: rpm             LE ×10
// Bytes 4-5: throttle_input  LE ×10
// Bytes 6-7: brake_input     LE ×10
static void decode_3A7(uint8_t* d) {
    battery_current = le16(d, 0) / 10.0f;
    rpm             = le16(d, 2) / 10.0f;
    throttle_input  = le16(d, 4) / 10.0f;
    brake_input     = le16(d, 6) / 10.0f;
}

// Curtis TPDO4 — 0x4A7
// Byte 0:    contactor_state  uint8
// Bytes 1-2: keyswitch_voltage LE ×10
static void decode_4A7(uint8_t* d) {
    contactor_state   = d[0];
    keyswitch_voltage = le16(d, 1) / 10.0f;
}

// BMS Pack — 0x200
// Bytes 0-1: voltage_pack BE ÷10
// Bytes 2-3: current_pack BE -30000 ÷10
// Bytes 4-5: soc          BE ÷10
static void decode_200(uint8_t* d) {
    voltage_pack = be16(d, 0) / 10.0f;
    current_pack = ((int16_t)be16(d, 2) - 30000) / 10.0f;
    soc          = be16(d, 4) / 10.0f;
}

// BMS Celdas — 0x201 a 0x204
// Cada trama tiene 4 celdas × 2 bytes BE en mV
// offset indica qué celda empieza (0, 4, 8, 12)
static void decode_cells(uint8_t* d, int offset) {
    for (int i = 0; i < 4; i++)
        cell_voltage[offset + i] = be16(d, i*2) / 1000.0f;
}

// BMS Temperaturas — 0x210
// Byte 0: temp_max int8
// Byte 1: temp_min int8
static void decode_210(uint8_t* d) {
    temp_max = (int8_t)d[0];
    temp_min = (int8_t)d[1];
}

// MDV GPS — 0x400
// Bytes 0-3: gps_lat LE ÷1,000,000
// Bytes 4-7: gps_lon LE ÷1,000,000
static void decode_400(uint8_t* d) {
    gps_lat = le32(d, 0) / 1000000.0f;
    gps_lon = le32(d, 4) / 1000000.0f;
}

// MDV Aceleración — 0x401
// Bytes 0-1: acc_x LE ÷100
// Bytes 2-3: acc_y LE ÷100
// Bytes 4-5: acc_z LE ÷100
static void decode_401(uint8_t* d) {
    acc_x = le16(d, 0) / 100.0f;
    acc_y = le16(d, 2) / 100.0f;
    acc_z = le16(d, 4) / 100.0f;
}

// MDV Giroscopio — 0x402
// Bytes 0-1: gyro_x LE ÷100
// Bytes 2-3: gyro_y LE ÷100
// Bytes 4-5: gyro_z LE ÷100
static void decode_402(uint8_t* d) {
    gyro_x = le16(d, 0) / 100.0f;
    gyro_y = le16(d, 2) / 100.0f;
    gyro_z = le16(d, 4) / 100.0f;
}

// MCA — 0x500
// Bytes 0-1: voltage_aux LE ÷100
// Bytes 2-3: current_aux LE ÷100
static void decode_500(uint8_t* d) {
    voltage_aux = le16(d, 0) / 100.0f;
    current_aux = le16(d, 2) / 100.0f;
}

// ─────────────────────────────────────────
//  TAREA T2
// ─────────────────────────────────────────
void taskProcessing(void* pvParameters) {
    twai_message_t msg;

    for (;;) {
        if (can_fifo_read(&msg)) {
            uint8_t* d = msg.data;
            switch (msg.identifier) {
                case 0x1A7: decode_1A7(d); break;
                case 0x2A7: decode_2A7(d); break;
                case 0x3A7: decode_3A7(d); break;
                case 0x4A7: decode_4A7(d); break;
                case 0x200: decode_200(d); break;
                case 0x201: decode_cells(d, 0);  break;
                case 0x202: decode_cells(d, 4);  break;
                case 0x203: decode_cells(d, 8);  break;
                case 0x204: decode_cells(d, 12); break;
                case 0x210: decode_210(d); break;
                case 0x400: decode_400(d); break;
                case 0x401: decode_401(d); break;
                case 0x402: decode_402(d); break;
                case 0x500: decode_500(d); break;
            }
        }
        vTaskDelay(pdMS_TO_TICKS(1));
    }
}