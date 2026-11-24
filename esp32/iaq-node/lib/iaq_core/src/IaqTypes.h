// Shared types for the XRPod IAQ node. No Arduino dependencies, so this
// library also builds and unit-tests on a PC (pio test -e native).
#pragma once

#include <math.h>
#include <stddef.h>
#include <stdint.h>

namespace xrpod {

// One BME688 reading.
struct IaqReading {
  float tempC;
  float humidityPct;
  float pressureHpa;
  float gasOhms;  // MOX gas resistance; drops when VOCs (scent) are present
};

}  // namespace xrpod
