#include "ScentDetector.h"

namespace xrpod {

ScentDetector::ScentDetector(const ScentDetectorConfig &cfg) : cfg_(cfg) {}

void ScentDetector::update(float gasOhms, bool scentActive) {
  if (isnan(gasOhms) || isinf(gasOhms) || gasOhms <= 0) return;  // bad read

  float drop = 0;
  if (baseline_ > 0) {
    drop = 1.0f - gasOhms / baseline_;
    if (drop < 0) drop = 0;
  }
  lastDrop_ = ready() ? drop : 0;

  // Learn the baseline only from clean air, so lingering scent after the
  // diffusers stop doesn't drag it down.
  bool cleanAir = !ready() || drop < cfg_.dropFraction;
  if (!scentActive && cleanAir) {
    baseline_ = baseline_ > 0 ? baseline_ + cfg_.baselineAlpha * (gasOhms - baseline_)
                              : gasOhms;
    if (samples_ < 0xFFFF) ++samples_;
  }

  if (!ready()) {
    consecutive_ = 0;
    detected_ = false;
    return;
  }
  if (drop >= cfg_.dropFraction) {
    if (consecutive_ < 0xFF) ++consecutive_;
  } else {
    consecutive_ = 0;
  }
  detected_ = consecutive_ >= cfg_.confirmSamples;
}

}  // namespace xrpod
