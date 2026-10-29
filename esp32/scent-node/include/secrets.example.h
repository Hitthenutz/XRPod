// Copy this file to secrets.h (same folder) and fill in real values.
// secrets.h is git-ignored so Wi-Fi passwords never get pushed to GitHub.
#pragma once

#define WIFI_SSID     "your-wifi-name"
#define WIFI_PASSWORD "your-wifi-password"

// Raspberry Pi 5 MQTT broker (Mosquitto) on the pod network
#define MQTT_HOST     "192.168.1.100"
#define MQTT_PORT     1883
#define MQTT_CLIENT_ID "xrpod-scent-node"
