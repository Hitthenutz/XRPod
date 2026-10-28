// XRPod scent / IAQ node (ESP32). Thin firmware: it reads two BME688s,
// publishes what they see, and runs an atomizer only when the hub on the Pi
// says so. Every decision (which scent, how strong, did it work) is made in
// pi/scent.py. MQTT contract: subsystems/iaq/docs/DESIGN.md.
//
// Fail-safe:
//   * atomizers off at boot, before Wi-Fi or sensors start,
//   * atomizers off whenever MQTT isn't connected,
//   * every command is capped at MAX_ON_S; the hub re-sends to keep going,
//   * at most one atomizer on at a time (atomizer.cpp).
#include <Arduino.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <WiFi.h>

#include "atomizer.h"
#include "config.h"
#include "secrets.h"
#include "sensors.h"

// ---------TOPICS---------
#define TOPIC(leaf) "xrpod/scent/" NODE_ID "/" leaf
const char *const STATUS_TOPIC = TOPIC("status");
const char *const CMD_TOPIC = TOPIC("cmd");
const char *const TELEMETRY_TOPIC = TOPIC("telemetry");
const char *const DETECT_TOPIC = TOPIC("detect");

WiFiClient net;
PubSubClient mqtt(net);
uint32_t lastReconnectMs = 0;
uint32_t lastTelemetryMs = 0;

void publishJson(const char *topic, const JsonDocument &doc) {
  char buf[512];
  size_t n = serializeJson(doc, buf, sizeof(buf));
  if (n == 0 || n >= sizeof(buf) || !mqtt.publish(topic, (const uint8_t *)buf, n)) {
    Serial.printf("# publish to %s failed\n", topic);
  }
}

// ---------COMMANDS FROM THE HUB---------
// {"atomizer": 0|1, "duty": 1-100, "on_s": 1-MAX_ON_S}  or  {"atomizer": -1}
void onMessage(char *topic, uint8_t *payload, unsigned int len) {
  if (strcmp(topic, CMD_TOPIC) != 0) return;
  JsonDocument doc;
  if (deserializeJson(doc, payload, len) || !doc["atomizer"].is<int>()) {
    Serial.println("# cmd rejected: not JSON with an integer \"atomizer\"");
    return;
  }
  int index = doc["atomizer"];
  if (index == -1) {
    atomizerOff();
    return;
  }
  if (!doc["duty"].is<int>() || !doc["on_s"].is<int>() || doc["on_s"].as<int>() <= 0 ||
      !atomizerStart(index, doc["duty"], doc["on_s"].as<int>(), millis())) {
    Serial.println("# cmd rejected: bad atomizer, duty or on_s");
  }
}

// ---------SENSOR DATA TO THE HUB---------
void publishTelemetry() {
  JsonDocument doc;
  const IaqReading &r = sensorsIaq();
  if (r.valid) {
    doc["t_c"] = r.tC;
    doc["rh"] = r.rh;
    doc["p_hpa"] = r.pHpa;
    doc["iaq"] = r.iaq;
    doc["iaq_acc"] = r.iaqAccuracy;
    doc["eco2_ppm"] = r.eco2Ppm;
    doc["bvoc_ppm"] = r.bvocPpm;
  }
  doc["atomizer"] = atomizerActive();
  doc["duty"] = atomizerDuty();
  doc["uptime_s"] = millis() / 1000;
  publishJson(TELEMETRY_TOPIC, doc);
}

void publishScan(const ScanReading &s) {
  if (!mqtt.connected()) return;
  JsonDocument doc;
  doc["t_c"] = s.tC;
  doc["rh"] = s.rh;
  doc["p_hpa"] = s.pHpa;
  JsonArray gas = doc["gas_ohm"].to<JsonArray>();
  for (int i = 0; i < s.steps; i++) gas.add(s.gasOhm[i]);
  JsonArray probs = doc["probs"].to<JsonArray>();
  for (int i = 0; i < GAS_CLASSES; i++) probs.add(s.probs[i]);
  doc["atomizer"] = atomizerActive();
  doc["duty"] = atomizerDuty();
  publishJson(DETECT_TOPIC, doc);
}

// ---------WI-FI + MQTT---------
void reconnect(uint32_t now) {
  if (WiFi.status() != WL_CONNECTED || now - lastReconnectMs < RECONNECT_MS) return;
  lastReconnectMs = now;
  // Last will: the broker marks us offline if we drop without saying so.
  if (!mqtt.connect(NODE_ID, MQTT_USER, MQTT_PASS, STATUS_TOPIC, 1, true, "offline")) {
    Serial.printf("# MQTT connect failed, state %d\n", mqtt.state());
    return;
  }
  mqtt.publish(STATUS_TOPIC, "online", true);
  mqtt.subscribe(CMD_TOPIC, 1);
  Serial.println("# MQTT connected");
}

void setup() {
  atomizerBegin();  // first: nothing runs until the hub asks
  Serial.begin(115200);
  Serial.println("# XRPod scent node " NODE_ID);

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMessage);
  mqtt.setBufferSize(512);
  mqtt.setSocketTimeout(2);

  sensorsBegin(publishScan);
}

void loop() {
  uint32_t now = millis();
  // Check Wi-Fi too: after a drop, the MQTT socket can look connected until
  // TCP times out.
  if (WiFi.status() == WL_CONNECTED && mqtt.connected()) {
    mqtt.loop();
  } else {
    atomizerOff();  // no hub, no scent
    reconnect(now);
  }

  sensorsRun();
  atomizerService(millis());

  if (mqtt.connected() && millis() - lastTelemetryMs >= TELEMETRY_MS) {
    lastTelemetryMs = millis();
    publishTelemetry();
  }
}
