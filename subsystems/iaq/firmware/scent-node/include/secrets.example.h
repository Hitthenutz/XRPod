// Copy to secrets.h (git-ignored) and fill in. Never commit secrets.h.
#pragma once

#define WIFI_SSID "your-pod-wifi"
#define WIFI_PASS "your-wifi-password"

// The Pi running Mosquitto (see subsystems/iaq/README.md).
#define MQTT_HOST "xrpod.local"
#define MQTT_PORT 1883
#define MQTT_USER "scent1"
#define MQTT_PASS "your-mqtt-password"
