#include "MqttLink.h"

static bool reached(uint32_t now, uint32_t at) { return static_cast<int32_t>(now - at) >= 0; }

void MqttLink::begin(const Settings &s, MessageHandler handler) {
  s_ = s;
  handler_ = handler;

  uint8_t mac[6];
  WiFi.macAddress(mac);
  snprintf(clientId_, sizeof(clientId_), "%s%02x%02x%02x", s_.clientIdPrefix, mac[3], mac[4],
           mac[5]);

  WiFi.persistent(false);  // don't wear flash rewriting credentials
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(s_.ssid, s_.password);

  mqtt_.setServer(s_.host, s_.port);
  mqtt_.setBufferSize(512);
  mqtt_.setKeepAlive(15);
  mqtt_.setSocketTimeout(3);  // bounds how long connect() can block
  mqtt_.setCallback([this](char *topic, uint8_t *payload, unsigned int len) {
    if (handler_ != nullptr) handler_(topic, payload, len);
  });

  started_ = true;
  Serial.printf("[net] client id %s, Wi-Fi %s\n", clientId_, s_.ssid);
}

void MqttLink::loop(uint32_t nowMs) {
  if (!started_) return;

  if (WiFi.status() != WL_CONNECTED) {
    if (reached(nowMs, nextWifiMs_)) {
      nextWifiMs_ = nowMs + s_.wifiRetryMs;
      Serial.println("[net] Wi-Fi down, reconnecting");
      WiFi.disconnect();
      WiFi.begin(s_.ssid, s_.password);
    }
    return;
  }

  if (!mqtt_.connected()) {
    if (reached(nowMs, nextMqttMs_)) {
      nextMqttMs_ = nowMs + s_.mqttRetryMs;
      tryConnect();
    }
    return;
  }

  mqtt_.loop();
}

void MqttLink::tryConnect() {
  Serial.printf("[mqtt] connecting to %s:%u ... ", s_.host, s_.port);
  bool ok = mqtt_.connect(clientId_, s_.user, s_.mqttPass, s_.statusTopic, 1, true, "offline");
  if (!ok) {
    Serial.printf("failed, rc=%d\n", mqtt_.state());
    return;
  }
  Serial.println("ok");
  mqtt_.subscribe(s_.subscribeTopic, 1);
  mqtt_.publish(s_.statusTopic, "online", true);
  justConnected_ = true;
}

bool MqttLink::publish(const char *topic, const char *payload, bool retained) {
  if (!mqtt_.connected()) return false;
  return mqtt_.publish(topic, payload, retained);
}

bool MqttLink::takeJustConnected() {
  bool v = justConnected_;
  justConnected_ = false;
  return v;
}
