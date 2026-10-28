// XRPod BME688 pair, both on one I2C bus, each with its own BSEC2 instance.
//   IAQ sensor:  Bosch stock IAQ config -> IAQ index, eCO2, bVOC, T/RH/P.
//   Scan sensor: AI-Studio config in gas-scan mode -> scent class
//                probabilities plus the raw gas resistance at each heater step.
// One BME688 can't run both configs at once, hence two sensors.
#pragma once

#include <stdint.h>

constexpr int MAX_SCAN_STEPS = 10;  // BSEC heater profiles have 1-10 steps
constexpr int GAS_CLASSES = 4;      // BSEC_OUTPUT_GAS_ESTIMATE_1..4

struct IaqReading {
  bool valid;
  float tC, rh, pHpa;
  float iaq;
  int iaqAccuracy;  // 0 = still calibrating ... 3 = calibrated
  float eco2Ppm, bvocPpm;
};

struct ScanReading {
  float tC, rh, pHpa;  // the scan sensor's own raw values
  int steps;
  float gasOhm[MAX_SCAN_STEPS];
  float probs[GAS_CLASSES];  // 0 everywhere while BSEC is still collecting
};

// Starts both sensors. A missing or failed sensor is logged and skipped;
// the other keeps working.
void sensorsBegin(void (*onScan)(const ScanReading &));

// Call every loop(). Calls onScan once per completed heater scan.
void sensorsRun();

const IaqReading &sensorsIaq();
