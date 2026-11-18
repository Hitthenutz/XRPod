// XRPod fan node (ESP32-S3): drives the Corsair RS120 fans (4-pin PWM) and
// reads their speed. Talks to the Pi over MQTT, like the scent node.
//
//   Pi --xrpod/fan/cmd-->   node   {"fan_speed_pct": 60}  (resent every 5 s)
//   Pi <--xrpod/fan/state-- node   {"fan_speed_pct","fan_rpm","uptime_s"} (retained, every 2 s)
//   Pi <--xrpod/fan/node--  node   "online" / "offline" (retained, last will)
//   Pi <--xrpod/fan/error-- node   {"error":"bad_json"}
//
// Fail-safe: no command from the Pi for 15 s -> fans off.
//
// Arduino IDE: board "ESP32S3 Dev Module". Libraries (Sketch > Include
// Library > Manage Libraries): "PubSubClient" by Nick O'Leary and
// "ArduinoJson" by Benoit Blanchon.

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ---- Fill these in before uploading, and never commit them ----------------
const char* WIFI_NAME = "PUT_WIFI_NAME_HERE";       // the Pi's hotspot, e.g. XRPod-Pi
const char* WIFI_PASSWORD = "PUT_WIFI_PASSWORD_HERE";
const char* MQTT_HOST = "10.42.0.1";                // the Pi (hotspot address)
const int MQTT_PORT = 1883;

// ---- Pins and timing --------------------------------------------------------
const int FAN_PIN = 4;   // fan pin 4 (PWM)
const int TACH_PIN = 5;  // fan pin 3 (tach)
const unsigned long COMMAND_TIMEOUT_MS = 15000;  // Pi resends every 5 s
const unsigned long STATE_PUBLISH_MS = 2000;
const unsigned long WIFI_RETRY_MS = 10000;
const unsigned long MQTT_RETRY_MS = 5000;

// ---- Topics (must match pi/fan.py and docs/subsystems.md) ------------------
const char* TOPIC_CMD = "xrpod/fan/cmd";
const char* TOPIC_STATE = "xrpod/fan/state";
const char* TOPIC_NODE = "xrpod/fan/node";
const char* TOPIC_ERROR = "xrpod/fan/error";

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
char clientId[32];

volatile unsigned long tachPulses = 0;
volatile unsigned long fellAtUs = 0;
volatile unsigned long countedAtUs = 0;
int fanPct = 0;
int fanRpm = 0;
unsigned long lastRpmMs = 0;
unsigned long lastCommandMs = 0;
unsigned long lastStateMs = 0;
unsigned long nextWifiMs = 0;
unsigned long nextMqttMs = 0;

// The tach wire picks up noise from the PWM wire next to it, so only count
// a pulse that stayed low for 1 ms, and at most one every 10 ms.
void IRAM_ATTR onTach() {
  unsigned long now = micros();
  if (digitalRead(TACH_PIN) == LOW) {
    fellAtUs = now;
  } else if (now - fellAtUs > 1000 && now - countedAtUs > 10000) {
    tachPulses++;
    countedAtUs = now;
  }
}

void setFan(int pct) {
  fanPct = constrain(pct, 0, 100);
  ledcWrite(FAN_PIN, fanPct * 255 / 100);
}

void publishState() {
  char buf[96];
  snprintf(buf, sizeof(buf), "{\"fan_speed_pct\":%d,\"fan_rpm\":%d,\"uptime_s\":%lu}",
           fanPct, fanRpm, millis() / 1000);
  mqtt.publish(TOPIC_STATE, buf, true);
  lastStateMs = millis();
}

void publishError(const char* error) {
  char buf[64];
  snprintf(buf, sizeof(buf), "{\"error\":\"%s\"}", error);
  mqtt.publish(TOPIC_ERROR, buf);
}

void onMessage(char* topic, byte* payload, unsigned int length) {
  if (strcmp(topic, TOPIC_CMD) != 0) return;
  JsonDocument doc;
  if (deserializeJson(doc, payload, length) != DeserializationError::Ok) {
    publishError("bad_json");
    return;
  }
  JsonVariant pct = doc["fan_speed_pct"];
  if (!pct.is<int>() || pct.as<int>() < 0 || pct.as<int>() > 100) {
    publishError("bad_fan_speed_pct");
    return;
  }
  lastCommandMs = millis();
  if (pct.as<int>() != fanPct) {
    setFan(pct.as<int>());
    Serial.printf("[fan] %d%%\n", fanPct);
    publishState();
  }
}

void keepConnected() {
  unsigned long now = millis();
  if (WiFi.status() != WL_CONNECTED) {
    if ((long)(now - nextWifiMs) >= 0) {
      nextWifiMs = now + WIFI_RETRY_MS;
      Serial.println("[net] Wi-Fi down, reconnecting");
      WiFi.disconnect();
      WiFi.begin(WIFI_NAME, WIFI_PASSWORD);
    }
    return;
  }
  if (!mqtt.connected()) {
    if ((long)(now - nextMqttMs) >= 0) {
      nextMqttMs = now + MQTT_RETRY_MS;
      Serial.printf("[mqtt] connecting to %s:%d ... ", MQTT_HOST, MQTT_PORT);
      if (mqtt.connect(clientId, nullptr, nullptr, TOPIC_NODE, 1, true, "offline")) {
        Serial.println("ok");
        mqtt.subscribe(TOPIC_CMD, 1);
        mqtt.publish(TOPIC_NODE, "online", true);
        publishState();
      } else {
        Serial.printf("failed, rc=%d\n", mqtt.state());
      }
    }
    return;
  }
  mqtt.loop();
}

void setup() {
  Serial.begin(115200);
  ledcAttach(FAN_PIN, 25000, 8);
  setFan(0);
  pinMode(TACH_PIN, INPUT_PULLUP);
  attachInterrupt(TACH_PIN, onTach, CHANGE);

  uint8_t mac[6];
  WiFi.macAddress(mac);
  snprintf(clientId, sizeof(clientId), "xrpod-fan-%02x%02x%02x", mac[3], mac[4], mac[5]);

  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_NAME, WIFI_PASSWORD);

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMessage);
  mqtt.setKeepAlive(15);
  mqtt.setSocketTimeout(3);
  Serial.printf("[net] client id %s, Wi-Fi %s\n", clientId, WIFI_NAME);
}

void loop() {
  keepConnected();
  unsigned long now = millis();

  // Fail-safe: the Pi stopped sending commands.
  if (fanPct > 0 && now - lastCommandMs > COMMAND_TIMEOUT_MS) {
    Serial.println("[fan] no command for 15 s: fans off");
    setFan(0);
    if (mqtt.connected()) publishState();
  }

  if (now - lastRpmMs >= 1000) {
    noInterrupts();
    unsigned long pulses = tachPulses;
    tachPulses = 0;
    interrupts();
    fanRpm = pulses * 30;  // 2 pulses per turn, counted over 1 s
    lastRpmMs = now;
  }

  if (mqtt.connected() && now - lastStateMs >= STATE_PUBLISH_MS) publishState();
}
