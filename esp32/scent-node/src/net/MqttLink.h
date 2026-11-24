// Wi-Fi + MQTT connection to the Raspberry Pi broker, with retry and a
// last-will "offline" message so the Pi knows when the node drops.
// MQTT_HOST can be an IP ("192.168.1.42") or an mDNS name ("xrpod.local").
#pragma once

#include <PubSubClient.h>
#include <WiFi.h>

class MqttLink {
 public:
  using MessageHandler = void (*)(const char *topic, const uint8_t *payload, unsigned int len);

  struct Settings {
    const char *ssid;
    const char *password;
    const char *host;
    uint16_t port;
    const char *user;      // nullptr = no login
    const char *mqttPass;  // nullptr = no login
    const char *clientIdPrefix;
    const char *subscribeTopic;
    const char *statusTopic;  // retained "online" / last-will "offline"
    uint32_t wifiRetryMs;
    uint32_t mqttRetryMs;
  };

  MqttLink() : mqtt_(wifi_) {}

  void begin(const Settings &s, MessageHandler handler);
  void loop(uint32_t nowMs);
  bool connected() { return mqtt_.connected(); }
  bool publish(const char *topic, const char *payload, bool retained = false);
  // True once right after each successful (re)connect.
  bool takeJustConnected();

  // Wi-Fi, broker and MQTT state in plain words (bench "net" command).
  void printNetStatus();
  // PubSubClient state code -> what it usually means.
  static const char *stateText(int rc);

 private:
  void tryConnect();
  bool resolveBroker();

  WiFiClient wifi_;
  PubSubClient mqtt_;
  Settings s_{};
  MessageHandler handler_ = nullptr;
  char clientId_[32] = {};
  IPAddress brokerIp_;
  bool useMdns_ = false;
  bool mdnsStarted_ = false;
  bool started_ = false;
  bool wifiWasUp_ = false;
  bool justConnected_ = false;
  int lastRc_ = MQTT_DISCONNECTED;
  uint32_t nextWifiMs_ = 0;
  uint32_t nextMqttMs_ = 0;
};
