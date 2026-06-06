#include "mqtt.h"
#include "../v_globals/globals.h"
#include "../../include/config.h"
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <esp_task_wdt.h>

#define MQTT_HOST      "23.94.237.163"
#define MQTT_PORT      1883
#define MQTT_USER      "fenix25"
#define MQTT_PASS      "pswTeleFenix"
#define MQTT_TOPIC     "fenix/mgt/snapshot"
#define MQTT_LWT_TOPIC "fenix/mgt/status"
#define MQTT_LWT_MSG   "offline"
#define VEHICLE_ID     25

static WiFiClient   wifiClient;
static PubSubClient mqttClient(wifiClient);

static bool serializar_snapshot(Snapshot& s, char* buf, size_t buf_size) {
    uint32_t  ms  = s.timestamp % 1000;
    time_t    seg = s.timestamp / 1000;
    struct tm t;
    localtime_r(&seg, &t);
    char ts[28];
    snprintf(ts, sizeof(ts), "%04d-%02d-%02d %02d:%02d:%02d.%03lu",
             t.tm_year + 1900, t.tm_mon + 1, t.tm_mday,
             t.tm_hour, t.tm_min, t.tm_sec, (unsigned long)ms);

    static JsonDocument doc;
    doc.clear();

    doc["veh_id"]    = VEHICLE_ID;
    doc["sess_id"]   = session_ID;
    doc["times"]     = ts;
    doc["curr_rms"]  = s.current_rms;
    doc["speed_v"]   = s.speed_vehicle;
    doc["odo_veh"]   = s.odometer_vehicle;
    doc["tmp_mot"]   = s.temp_motor;
    doc["tmp_cont"]  = s.temp_ctrl;
    doc["tmp_cap"]   = s.temp_capacitors;
    doc["mot_torq"]  = s.motor_torque;
    doc["batt_curr"] = s.battery_current;
    doc["rpm"]       = s.rpm;
    doc["throttle"]  = s.throttle_input;
    doc["brake"]     = s.brake_input;
    doc["cont_st"]   = s.contactor_state;
    doc["ksy_v"]     = s.keyswitch_voltage;
    doc["volt_p"]    = s.voltage_pack;
    doc["curr_p"]    = s.current_pack;
    doc["soc"]       = s.soc;

    JsonArray cells = doc["cell_volts"].to<JsonArray>();
    for (int i = 0; i < 16; i++) cells.add(s.cell_voltage[i]);

    doc["tmp_max"] = s.temp_max;
    doc["tmp_min"] = s.temp_min;
    doc["gps_lat"] = s.gps_lat;
    doc["gps_lon"] = s.gps_lon;
    doc["acc_x"]   = s.acc_x;
    doc["acc_y"]   = s.acc_y;
    doc["acc_z"]   = s.acc_z;
    doc["gyro_x"]  = s.gyro_x;
    doc["gyro_y"]  = s.gyro_y;
    doc["gyro_z"]  = s.gyro_z;
    doc["volt_a"]  = s.voltage_aux;
    doc["curr_a"]  = s.current_aux;

    return serializeJson(doc, buf, buf_size) > 0;
}

static bool mqtt_conectar() {
    esp_task_wdt_reset();
    mqttClient.disconnect();
    vTaskDelay(pdMS_TO_TICKS(200));
    esp_task_wdt_reset();

    if (mqttClient.connect("MGT_Fenix25", MQTT_USER, MQTT_PASS,
                           MQTT_LWT_TOPIC, 0, true, MQTT_LWT_MSG)) {
        mqtt_conectado = true;
        mqtt_tx_on     = true;
        Serial.println("[T4] MQTT conectado");
        esp_task_wdt_reset();
        return true;
    }
    mqtt_conectado = false;
    mqtt_tx_on     = false;
    Serial.print("[T4] MQTT fallo — estado: ");
    Serial.println(mqttClient.state());
    esp_task_wdt_reset();
    return false;
}

void taskMQTT(void* pvParameters) {
    Serial.println("[T4] MQTT iniciada");

    mqttClient.setServer(MQTT_HOST, MQTT_PORT);
    mqttClient.setBufferSize(1024);
    mqttClient.setKeepAlive(10);
    mqttClient.setSocketTimeout(2);

    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    Serial.print("[T4] Conectando WiFi");

    uint32_t t_wifi = millis();
    while (WiFi.status() != WL_CONNECTED) {
        vTaskDelay(pdMS_TO_TICKS(500));
        Serial.print(".");
        if (millis() - t_wifi > 15000) {
            Serial.println("\n[T4] WiFi timeout");
            break;
        }
    }

    if (WiFi.status() == WL_CONNECTED) {
        mqtt_wifi_ok = true;
        Serial.print("\n[T4] WiFi OK — IP: ");
        Serial.println(WiFi.localIP());
        mqtt_conectar();
    }

    uint32_t t_ultimo_pub = 0;
    uint32_t t_reconexion = 0;
    char     json_buf[1024];

    for (;;) {
        uint32_t ahora = millis();

        if (WiFi.status() != WL_CONNECTED) {
            mqtt_wifi_ok   = false;
            mqtt_conectado = false;
            mqtt_tx_on     = false;

            if (ahora - t_reconexion >= 5000) {
                t_reconexion = ahora;
                Serial.println("[T4] Reconectando WiFi...");
                WiFi.reconnect();
            }

        } else {
            mqtt_wifi_ok = true;

            if (!mqttClient.connected()) {
                mqtt_conectado = false;
                mqtt_tx_on     = false;

                if (ahora - t_reconexion >= 5000) {
                    t_reconexion = ahora;
                    Serial.println("[T4] Reconectando MQTT...");
                    mqtt_conectar();
                }
            } else {
                mqtt_conectado = true;
                mqttClient.loop();
            }
        }

        if (mqtt_conectado && ahora - t_ultimo_pub >= 100) {
            t_ultimo_pub = ahora;

            Snapshot s_local;
            bool tiene_snapshot = false;

            if (xSemaphoreTake(snap_mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
                if (snap_count > 0) {
                    s_local        = snap_buffer[snap_count - 1];
                    tiene_snapshot = true;
                }
                xSemaphoreGive(snap_mutex);
            }

            if (tiene_snapshot) {
                if (serializar_snapshot(s_local, json_buf, sizeof(json_buf))) {
                    if (mqttClient.publish(MQTT_TOPIC, json_buf)) {
                        mqtt_publicaciones++;
                        mqtt_tx_on = true;
                    }
                }
            }
        }

        vTaskDelay(pdMS_TO_TICKS(10));
    }
}