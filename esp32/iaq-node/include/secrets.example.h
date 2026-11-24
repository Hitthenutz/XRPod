// Copy this file to secrets.h (same folder) and fill in real values.
// secrets.h is git-ignored so Wi-Fi and MQTT passwords never get pushed.
// Without secrets.h the node runs offline: it still reads the BME688 and
// prints every reading over USB, which is enough to test the wiring.
#pragma once

// The Pi's hotspot (2.4 GHz). Same values as the scent and fan nodes.
#define WIFI_SSID     "XRPod-Pi"
#define WIFI_PASSWORD "your-hotspot-password"

// Mosquitto on the Pi. On the Pi's own hotspot the Pi is 10.42.0.1.
#define MQTT_HOST     "10.42.0.1"
#define MQTT_PORT     1883

// The broker login, if it needs one (same as the other nodes use).
// #define MQTT_USER     "xrpod"
// #define MQTT_PASSWORD "change-me"
