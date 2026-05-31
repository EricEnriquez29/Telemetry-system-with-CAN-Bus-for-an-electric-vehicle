#include "can.h"
#include "../../include/config.h"

// ─────────────────────────────────────────
//  BUFFER FIFO CAN — 150 posiciones AAA
// ─────────────────────────────────────────
static twai_message_t can_fifo[150];
static int fifo_head = 0, fifo_tail = 0, fifo_count = 0;

bool can_fifo_read(twai_message_t* msg) {
    if (fifo_count == 0) return false;
    *msg      = can_fifo[fifo_head];
    fifo_head = (fifo_head + 1) % 150;
    fifo_count--;
    return true;
}

int can_fifo_size() { return fifo_count; }

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

uint32_t can_count(uint16_t id) {
    int idx = id_index(id);
    return idx >= 0 ? cnt[idx] : 0;
}

uint32_t can_total() { return total; }

void can_snapshot_counts(uint32_t* buf) {
    for (int i = 0; i < 14; i++) buf[i] = cnt[i];
}

// ─────────────────────────────────────────
//  TAREA T1
// ─────────────────────────────────────────
void taskCAN(void* pvParameters) {
    twai_general_config_t g = TWAI_GENERAL_CONFIG_DEFAULT(
        (gpio_num_t)CAN_TX, (gpio_num_t)CAN_RX, TWAI_MODE_NORMAL);
    twai_timing_config_t  t = TWAI_TIMING_CONFIG_500KBITS();
    twai_filter_config_t  f = TWAI_FILTER_CONFIG_ACCEPT_ALL();

    if (twai_driver_install(&g, &t, &f) != ESP_OK) { vTaskDelete(NULL); }
    if (twai_start()                    != ESP_OK) { vTaskDelete(NULL); }

    twai_message_t nmt;
    nmt.identifier       = 0x000;
    nmt.data_length_code = 2;
    nmt.extd             = 0;
    nmt.rtr              = 0;
    nmt.data[0]          = 0x01;
    nmt.data[1]          = 0x27;
    twai_transmit(&nmt, pdMS_TO_TICKS(10));

    twai_message_t msg;
    for (;;) {
        if (twai_receive(&msg, pdMS_TO_TICKS(10)) == ESP_OK) {
            int idx = id_index(msg.identifier);
            if (idx < 0) { vTaskDelay(pdMS_TO_TICKS(1)); continue; }

            cnt[idx]++; total++;

            if (fifo_count < 150) {
                can_fifo[fifo_tail] = msg;
                fifo_tail  = (fifo_tail + 1) % 150;
                fifo_count++;
            }
        }
        vTaskDelay(pdMS_TO_TICKS(1));
    }
}
