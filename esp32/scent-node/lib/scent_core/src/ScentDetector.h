// First-pass scent verification from the BME688 gas resistance.
//
// MOX gas resistance drops when VOCs (scent oils) are in the air. While no
// scent is active and the air looks clean, we track a slow baseline. When the
// reading falls `dropFraction` below that baseline for `confirmSamples`
// readings in a row, we report the scent as detected.
//
// Limitations: humidity and temperature also move gas resistance, and the
// sensor needs several minutes to settle after power-up. Replace this with
// Bosch BSEC2 (IAQ / bVOC outputs) once the basic loop works.
#pragma once

#include "ScentTypes.h"

namespace xrpod {

struct ScentDetectorConfig {
  uint16_t warmupSamples;   // clean-air samples before we trust the baseline
  float baselineAlpha;      // EMA weight for each new clean-air sample
  float dropFraction;       // e.g. 0.25 = 25 % below baseline means detected
  uint8_t confirmSamples;   // consecutive samples needed to flip detected
};

constexpr ScentDetectorConfig kDefaultDetectorConfig = {20, 0.05f, 0.25f, 2};

class ScentDetector {
 public:
  explicit ScentDetector(const ScentDetectorConfig &cfg = kDefaultDetectorConfig);

  void update(float gasOhms, bool scentActive);

  bool ready() const { return samples_ >= cfg_.warmupSamples; }
  bool detected() const { return detected_; }
  float baselineOhms() const { return baseline_; }
  // How far the last reading was below baseline (0.3 = 30 %); 0 if not ready.
  float lastDrop() const { return lastDrop_; }

 private:
  ScentDetectorConfig cfg_;
  float baseline_ = 0;
  float lastDrop_ = 0;
  uint16_t samples_ = 0;
  uint8_t consecutive_ = 0;
  bool detected_ = false;
};

}  // namespace xrpod
