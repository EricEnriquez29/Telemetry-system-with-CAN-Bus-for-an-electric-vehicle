#pragma once
#include <Arduino.h>

// Inicializa WiFi y arranca la tarea MQTT en el núcleo 0
void taskMQTT(void* pvParameters);