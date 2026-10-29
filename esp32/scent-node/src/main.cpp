// XRPod scent / IAQ node - starter firmware
// Blinks the on-board LED, prints a heartbeat over serial, and (once secrets.h
// is filled in) connects to Wi-Fi and the Raspberry Pi MQTT broker.

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>

#if __has_include("secrets.h")
#include "secrets.h"
#define HAVE_SECRETS 1
#else
#include "secrets.example.h"
#define HAVE_SECRETS 0
#endif

#ifndef LED_BUILTIN
#define LED_BUILTIN 2  // most WROOM-32 DevKits use GPIO2
#endif

static const char *TOPIC_STATUS = "xrpod/scent/status";
static const char *TOPIC_CMD    = "xrpod/scent/cmd";

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

void onMqttMessage(char *topic, byte *payload, unsigned int len) {
  Serial.printf("[mqtt] %s: %.*s\n", topic, (int)len, (const char *)payload);
  // TODO: parse scent command (scent id + intensity) and drive atomizers
}

void connectWifi() {
  if (!HAVE_SECRETS || WiFi.status() == WL_CONNECTED) return;
  Serial.printf("[wifi] connecting to %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 10000) {
    delay(250);
    Serial.print('.');
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print(" ok, IP ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println(" failed (will retry)");
  }
}

void connectMqtt() {
  if (!HAVE_SECRETS || WiFi.status() != WL_CONNECTED || mqtt.connected()) return;
  Serial.printf("[mqtt] connecting to %s:%d ... ", MQTT_HOST, MQTT_PORT);
  if (mqtt.connect(MQTT_CLIENT_ID)) {
    Serial.println("ok");
    mqtt.subscribe(TOPIC_CMD);
    mqtt.publish(TOPIC_STATUS, "online");
  } else {
    Serial.printf("failed, rc=%d\n", mqtt.state());
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.println("\nXRPod scent node booting");
  Serial.printf("Chip: %s rev %d, %d MHz, flash %lu KB\n", ESP.getChipModel(),
                ESP.getChipRevision(), ESP.getCpuFreqMHz(),
                (unsigned long)(ESP.getFlashChipSize() / 1024));
  if (!HAVE_SECRETS) Serial.println("No secrets.h yet - running offline (blink only)");

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMqttMessage);
}

void loop() {
  static uint32_t lastBeat = 0, lastRetry = 0;
  uint32_t now = millis();

  if (now - lastRetry > 5000) {
    lastRetry = now;
    connectWifi();
    connectMqtt();
  }
  mqtt.loop();

  if (now - lastBeat > 1000) {
    lastBeat = now;
    digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
    Serial.printf("heartbeat %lus\n", (unsigned long)(now / 1000));
  }
}
