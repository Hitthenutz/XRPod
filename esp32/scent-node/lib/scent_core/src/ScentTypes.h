// Shared types for the XRPod scent node. No Arduino dependencies, so this
// library also builds and unit-tests on a PC (pio test -e native).
#pragma once

#include <math.h>
#include <stddef.h>
#include <stdint.h>

namespace xrpod {

constexpr uint8_t kMaxSlots = 8;
constexpr uint8_t kMaxDiffusersPerSlot = 4;
constexpr int8_t kNoScent = -1;

// One scent cartridge and the GPIO pins of its diffusers (atomizers).
// Only the first `diffusersPerSlot` pins are used; the rest are ignored.
struct ScentSlot {
  const char *name;  // must match SCENTS in pi/store.py
  uint8_t pins[kMaxDiffusersPerSlot];
};

// What the Pi asked for. slot == kNoScent means everything off.
struct ScentCommand {
  int8_t slot;
  uint8_t intensityPct;
};

constexpr ScentCommand kScentOff = {kNoScent, 0};

// One BME688 reading.
struct IaqReading {
  float tempC;
  float humidityPct;
  float pressureHpa;
  float gasOhms;  // MOX gas resistance; drops when VOCs (scent) are present
};

// Same rule as to_pct() in pi/hardware.py: anything that isn't a
// finite number becomes 0 (off); otherwise truncate and clamp to 0-100.
inline uint8_t clampPct(double v) {
  if (isnan(v) || isinf(v) || v <= 0) return 0;
  if (v >= 100) return 100;
  return static_cast<uint8_t>(v);
}

}  // namespace xrpod
