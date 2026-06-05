#pragma once
#include <Arduino.h>
#include "driver/twai.h"

void     taskCAN             (void* pvParameters);
bool     can_fifo_read       (twai_message_t* msg);
int      can_fifo_size       ();
bool     can_status          ();
uint32_t can_count           (uint16_t id);
uint32_t can_total           ();
void     can_snapshot_counts (uint32_t* buf);
bool     can_bus_off         ();
uint8_t  can_rec             ();
void     can_reinicializar   ();