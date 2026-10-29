// Copy this file to secrets.h (same folder) and fill in real values.
// secrets.h is git-ignored so Wi-Fi passwords never get pushed to GitHub.
// Without secrets.h the node runs offline: outputs stay off, sensor still logs.
#pragma once

#define WIFI_SSID     "your-wifi-name"
#define WIFI_PASSWORD "your-wifi-password"

// Raspberry Pi 5 MQTT broker (Mosquitto) on the pod network
// Use the Pi's IP; ".local" names may not resolve on the ESP32
#define MQTT_HOST     "192.168.1.100"
#define MQTT_PORT     1883

// Optional: uncomment if the broker requires a login
// #define MQTT_USER     "scent-node"
// #define MQTT_PASSWORD "change-me"
