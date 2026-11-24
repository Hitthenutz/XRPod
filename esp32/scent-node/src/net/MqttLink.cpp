#include "MqttLink.h"

#include <ESPmDNS.h>
#include <string.h>

static bool reached(uint32_t now, uint32_t at) { return static_cast<int32_t>(now - at) >= 0; }

static bool endsWith(const char *s, const char *suffix) {
  size_t n = strlen(s), m = strlen(suffix);
  return n >= m && strcasecmp(s + n - m, suffix) == 0;
}

const char *MqttLink::stateText(int rc) {
  switch (rc) {
    case MQTT_CONNECTION_TIMEOUT: return "no reply from broker (wrong IP, or Mosquitto not listening on the network)";
    case MQTT_CONNECTION_LOST: return "connection lost";
    case MQTT_CONNECT_FAILED: return "can't reach broker (wrong IP/port, Pi off, or firewall)";
    case MQTT_DISCONNECTED: return "disconnected";
    case MQTT_CONNECTED: return "connected";
    case MQTT_CONNECT_BAD_PROTOCOL: return "bad protocol";
    case MQTT_CONNECT_BAD_CLIENT_ID: return "client id rejected";
    case MQTT_CONNECT_UNAVAILABLE: return "broker unavailable";
    case MQTT_CONNECT_BAD_CREDENTIALS: return "bad username/password";
    case MQTT_CONNECT_UNAUTHORIZED: return "not authorized (broker needs a login - set MQTT_USER)";
  }
  return "unknown";
}

void MqttLink::begin(const Settings &s, MessageHandler handler) {
  s_ = s;
  handler_ = handler;
  useMdns_ = endsWith(s_.host, ".local");

  uint8_t mac[6];
  WiFi.macAddress(mac);
  snprintf(clientId_, sizeof(clientId_), "%s%02x%02x%02x", s_.clientIdPrefix, mac[3], mac[4],
           mac[5]);

  WiFi.persistent(false);  // don't wear flash rewriting credentials
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(clientId_);  // shows up in the router's device list
  WiFi.setAutoReconnect(true);
  WiFi.begin(s_.ssid, s_.password);
  nextWifiMs_ = millis() + s_.wifiRetryMs;  // give the first attempt time

  mqtt_.setBufferSize(512);
  mqtt_.setKeepAlive(15);
  mqtt_.setSocketTimeout(3);  // bounds how long connect() can block
  mqtt_.setCallback([this](char *topic, uint8_t *payload, unsigned int len) {
    if (handler_ != nullptr) handler_(topic, payload, len);
  });

  started_ = true;
  Serial.printf("[net] client id %s, joining Wi-Fi \"%s\", broker %s:%u\n", clientId_, s_.ssid,
                s_.host, s_.port);
}

void MqttLink::loop(uint32_t nowMs) {
  if (!started_) return;

  bool wifiUp = WiFi.status() == WL_CONNECTED;
  if (wifiUp != wifiWasUp_) {
    wifiWasUp_ = wifiUp;
    if (wifiUp) {
      Serial.printf("[net] Wi-Fi connected: IP %s, signal %d dBm\n",
                    WiFi.localIP().toString().c_str(), WiFi.RSSI());
      if (useMdns_ && !mdnsStarted_) mdnsStarted_ = MDNS.begin(clientId_);
      nextMqttMs_ = nowMs;  // try the broker right away
    } else {
      Serial.println("[net] Wi-Fi lost");
    }
  }

  if (!wifiUp) {
    if (reached(nowMs, nextWifiMs_)) {
      nextWifiMs_ = nowMs + s_.wifiRetryMs;
      Serial.printf("[net] Wi-Fi \"%s\" not connected (status %d) - retrying. "
                    "Type 'scan' to see nearby networks.\n",
                    s_.ssid, static_cast<int>(WiFi.status()));
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

bool MqttLink::resolveBroker() {
  if (!useMdns_) {
    if (!brokerIp_.fromString(s_.host)) {
      // A normal DNS name: let WiFiClient resolve it.
      mqtt_.setServer(s_.host, s_.port);
      return true;
    }
  } else {
    // "xrpod.local" -> ask the network via mDNS (the Pi answers for itself).
    char name[48];
    strncpy(name, s_.host, sizeof(name) - 1);
    name[sizeof(name) - 1] = '\0';
    name[strlen(name) - strlen(".local")] = '\0';
    IPAddress ip = MDNS.queryHost(name, 2000);
    if (ip == IPAddress(0, 0, 0, 0)) {
      Serial.printf("[mqtt] couldn't find %s on the network (mDNS) - use the Pi's IP instead\n",
                    s_.host);
      return false;
    }
    brokerIp_ = ip;
  }
  mqtt_.setServer(brokerIp_, s_.port);
  return true;
}

void MqttLink::tryConnect() {
  if (!resolveBroker()) return;
  Serial.printf("[mqtt] connecting to %s:%u (%s) ... ", s_.host, s_.port,
                brokerIp_.toString().c_str());
  bool ok = mqtt_.connect(clientId_, s_.user, s_.mqttPass, s_.statusTopic, 1, true, "offline");
  lastRc_ = mqtt_.state();
  if (!ok) {
    Serial.printf("failed: %s (rc=%d)\n", stateText(lastRc_), lastRc_);
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

void MqttLink::printNetStatus() {
  if (!started_) {
    Serial.println("network  : off (no secrets.h, or placeholder values in it)");
    return;
  }
  Serial.printf("wifi     : \"%s\" %s", s_.ssid,
                WiFi.status() == WL_CONNECTED ? "connected" : "NOT connected");
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf(", IP %s, gateway %s, signal %d dBm", WiFi.localIP().toString().c_str(),
                  WiFi.gatewayIP().toString().c_str(), WiFi.RSSI());
  }
  Serial.println();
  Serial.printf("broker   : %s:%u", s_.host, s_.port);
  if (brokerIp_ != IPAddress(0, 0, 0, 0)) Serial.printf(" -> %s", brokerIp_.toString().c_str());
  Serial.println();
  int rc = mqtt_.state();
  Serial.printf("mqtt     : %s (rc=%d), client id %s\n", stateText(rc), rc, clientId_);
}
