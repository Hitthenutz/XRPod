// XRPod scent node: pins, timing and MQTT topics. Change these to match the
// build. Wi-Fi / broker details live in secrets.h (git-ignored).
#pragma once

#include <ScentTypes.h>

namespace cfg {

// ---- Scents ---------------------------------------------------------------
// Names must match SCENTS in pi-agent/store.py. 3 scents x 2 diffusers.
// Each pin drives a logic-level N-MOSFET (low-side) switching one 5 V USB
// atomizer. Put a 10k pull-down on each gate so outputs stay off at boot.
// Pins avoid ESP32 strapping pins (0, 2, 5, 12, 15), flash pins (6-11) and
// input-only pins (34-39).
// TODO(hardware): confirm the Starry modules mist on power-up; if they need a
// button press, the MOSFET has to pulse the button instead.
constexpr uint8_t kNumScents = 3;
constexpr uint8_t kDiffusersPerScent = 2;
static const xrpod::ScentSlot kScents[kNumScents] = {
    {"lavender", {25, 26}},
    {"pine", {27, 13}},
    {"citrus", {32, 33}},
};
constexpr bool kOutputsActiveLow = false;  // true for active-low relay boards

constexpr uint32_t kDutyWindowMs = 10000;     // intensity cycle length
constexpr uint32_t kCommandTimeoutMs = 15000; // Pi must resend within this

// ---- BME688 (I2C) -----------------------------------------------------------
constexpr uint8_t kI2cSda = 21;
constexpr uint8_t kI2cScl = 22;
constexpr uint8_t kBmeAddress = 0x77;  // 0x76 if SDO is tied to GND
constexpr uint32_t kSensorPeriodMs = 3000;
constexpr uint16_t kGasHeaterC = 320;
constexpr uint16_t kGasHeaterMs = 150;

// ---- MQTT -------------------------------------------------------------------
constexpr const char *kTopicCmd = "xrpod/scent/cmd";        // Pi -> node
constexpr const char *kTopicState = "xrpod/scent/state";    // node -> Pi, retained
constexpr const char *kTopicNode = "xrpod/scent/node";      // "online"/"offline", retained (LWT)
constexpr const char *kTopicError = "xrpod/scent/error";    // node -> Pi
constexpr const char *kTopicReading = "xrpod/iaq/reading";  // node -> Pi
constexpr const char *kClientIdPrefix = "xrpod-scent-";
constexpr uint32_t kStatePublishMs = 5000;  // also publishes on every change
constexpr uint32_t kWifiRetryMs = 10000;
constexpr uint32_t kMqttRetryMs = 5000;

constexpr uint8_t kStatusLed = 2;  // on-board LED on most WROOM-32 DevKits

}  // namespace cfg
