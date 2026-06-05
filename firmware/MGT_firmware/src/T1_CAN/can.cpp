#include "can.h"
#include "../../include/config.h"

// ─────────────────────────────────────────
//  MUTEX FIFO
// ─────────────────────────────────────────
static SemaphoreHandle_t fifo_mutex = NULL;
static SemaphoreHandle_t cnt_mutex  = NULL;

// ─────────────────────────────────────────
//  BUFFER FIFO CAN — 150 posiciones
// ─────────────────────────────────────────
static twai_message_t can_fifo[150];
static int fifo_head = 0, fifo_tail = 0, fifo_count = 0;

bool can_fifo_read(twai_message_t* msg) {
    if (fifo_mutex == NULL) return false;
    if (xSemaphoreTake(fifo_mutex, pdMS_TO_TICKS(5)) != pdTRUE) return false;
    if (fifo_count == 0) {
        xSemaphoreGive(fifo_mutex);
        return false;
    }
    *msg      = can_fifo[fifo_head];
    fifo_head = (fifo_head + 1) % 150;
    fifo_count--;
    xSemaphoreGive(fifo_mutex);
    return true;
}

int can_fifo_size() {
    if (fifo_mutex == NULL) return 0;
    if (xSemaphoreTake(fifo_mutex, pdMS_TO_TICKS(5)) != pdTRUE) return 0;
    int size = fifo_count;
    xSemaphoreGive(fifo_mutex);
    return size;
}

// ─────────────────────────────────────────
//  CONTADORES POR ID
// ─────────────────────────────────────────
static uint32_t cnt[14] = {0};
static uint32_t total   = 0;

static int id_index(uint32_t id) {
    switch (id) {
        case 0x1A7: return 0;  case 0x2A7: return 1;
        case 0x3A7: return 2;  case 0x4A7: return 3;
        case 0x200: return 4;  case 0x201: return 5;
        case 0x202: return 6;  case 0x203: return 7;
        case 0x204: return 8;  case 0x210: return 9;
        case 0x400: return 10; case 0x401: return 11;
        case 0x402: return 12; case 0x500: return 13;
        default:    return -1;
    }
}

bool can_status() {
    twai_status_info_t s;
    return (twai_get_status_info(&s) == ESP_OK &&
            s.state == TWAI_STATE_RUNNING);
}

bool can_bus_off() {
    twai_status_info_t s;
    return (twai_get_status_info(&s) == ESP_OK &&
            s.state == TWAI_STATE_BUS_OFF);
}

uint8_t can_rec() {
    twai_status_info_t s;
    if (twai_get_status_info(&s) != ESP_OK) return 0;
    return (uint8_t)s.rx_error_counter;
}

uint32_t can_count(uint16_t id) {
    int idx = id_index(id);
    if (idx < 0) return 0;
    if (cnt_mutex == NULL) return cnt[idx];
    if (xSemaphoreTake(cnt_mutex, pdMS_TO_TICKS(5)) != pdTRUE) return cnt[idx];
    uint32_t v = cnt[idx];
    xSemaphoreGive(cnt_mutex);
    return v;
}

uint32_t can_total() {
    if (cnt_mutex == NULL) return total;
    if (xSemaphoreTake(cnt_mutex, pdMS_TO_TICKS(5)) != pdTRUE) return total;
    uint32_t v = total;
    xSemaphoreGive(cnt_mutex);
    return v;
}

void can_snapshot_counts(uint32_t* buf) {
    if (cnt_mutex == NULL) {
        for (int i = 0; i < 14; i++) buf[i] = cnt[i];
        return;
    }
    if (xSemaphoreTake(cnt_mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
        for (int i = 0; i < 14; i++) buf[i] = cnt[i];
        xSemaphoreGive(cnt_mutex);
    } else {
        for (int i = 0; i < 14; i++) buf[i] = cnt[i];
    }
}

// ─────────────────────────────────────────
//  REINICIALIZACIÓN TWAI — Bus-Off
// ─────────────────────────────────────────
void can_reinicializar() {
    Serial.println("[T1] Bus-Off — iniciando recuperacion TWAI");
    twai_initiate_recovery();
    Serial.println("[T1] Recuperacion TWAI iniciada");
}

// ─────────────────────────────────────────
//  TAREA T1
// ─────────────────────────────────────────
void taskCAN(void* pvParameters) {
    fifo_mutex = xSemaphoreCreateMutex();
    cnt_mutex  = xSemaphoreCreateMutex();

    twai_general_config_t g = TWAI_GENERAL_CONFIG_DEFAULT(
        (gpio_num_t)CAN_TX, (gpio_num_t)CAN_RX, TWAI_MODE_NORMAL);
    twai_timing_config_t  t = TWAI_TIMING_CONFIG_500KBITS();
    twai_filter_config_t  f = TWAI_FILTER_CONFIG_ACCEPT_ALL();

    if (twai_driver_install(&g, &t, &f) != ESP_OK) { vTaskDelete(NULL); }
    if (twai_start()                    != ESP_OK) { vTaskDelete(NULL); }

    twai_message_t nmt;
    nmt.identifier       = 0x000;
    nmt.data_length_code = 2;
    nmt.data[0]          = 0x01;
    nmt.data[1]          = 0x27;
    twai_transmit(&nmt, pdMS_TO_TICKS(10));

    twai_message_t msg;
    for (;;) {
        // ── Detectar y recuperar Bus-Off ──
        if (can_bus_off()) {
            can_reinicializar();
        }

        if (twai_receive(&msg, pdMS_TO_TICKS(10)) == ESP_OK) {
            int idx = id_index(msg.identifier);
            if (idx < 0) continue;

            if (cnt_mutex == NULL) {
                cnt[idx]++; total++;
            } else if (xSemaphoreTake(cnt_mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
                cnt[idx]++; total++;
                xSemaphoreGive(cnt_mutex);
            } else {
                // fallback if mutex can't be taken
                cnt[idx]++; total++;
            }

            if (xSemaphoreTake(fifo_mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
                if (fifo_count < 150) {
                    can_fifo[fifo_tail] = msg;
                    fifo_tail  = (fifo_tail + 1) % 150;
                    fifo_count++;
                }
                xSemaphoreGive(fifo_mutex);
            }
        }
    }
}