#pragma once

#define CAN_TX      21
#define CAN_RX      22
#define LED_VERDE   14   // Parpadeo 500ms — RUN
#define LED_AZUL    27   // Parpadeo 500ms con CAN / apagado sin CAN
#define LED_ROJO    26   // Fijo si hay error CAN
#define LED_AMARILLO 25  // Parpadeo 200ms con MQTT activo / apagado sin MQTT