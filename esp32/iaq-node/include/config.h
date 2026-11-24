// XRPod IAQ node: pins, timing and MQTT topics. Wi-Fi / broker details live
// in secrets.h (git-ignored).
#pragma once

#include <stdint.h>

namespace cfg {

// ---- BME688 (I2C) -----------------------------------------------------------
// This ESP32's own pins. Power the sensor from THIS board's 3V3 (not 5V, and
// never join two ESP32s' 3V3 pins). Sharing GND with the scent ESP32 on the
// same breadboard is fine.
constexpr uint8_t kI2cSda = 21;
constexpr uint8_t kI2cScl = 22;
// Tried in this order: 0x77 (Adafruit, most boards) then 0x76 (Pimoroni, or
// SDO tied to GND). Whichever answers is used.
constexpr uint8_t kBmeAddresses[] = {0x77, 0x76};
constexpr uint32_t kSensorPeriodMs = 3000;
constexpr uint16_t kGasHeaterC = 320;
constexpr uint16_t kGasHeaterMs = 150;

// ---- MQTT -------------------------------------------------------------------
// Readings go where the Pi already listens (pi/scent.py, docs/subsystems.md).
constexpr const char *kTopicReading = "xrpod/iaq/reading";  // node -> Pi
constexpr const char *kTopicNode = "xrpod/iaq/node";        // "online"/"offline", retained (last will)
// Listened to, so scent detection knows when a scent is meant to be on.
constexpr const char *kTopicScentState = "xrpod/scent/state";
constexpr const char *kClientIdPrefix = "xrpod-iaq-";
constexpr uint32_t kWifiRetryMs = 10000;
constexpr uint32_t kMqttRetryMs = 5000;

constexpr uint8_t kStatusLed = 2;  // on-board LED on most WROOM-32 DevKits

}  // namespace cfg
