// JSON messages the node publishes to the Pi.
//
// xrpod/scent/state (retained):
//   {"selected_scent":"lavender","scent_intensity_pct":60,
//    "diffusers":[true,false],"reason":"command","uptime_s":123}
// xrpod/iaq/reading:
//   {"temp_c":22.4,"humidity_pct":41.2,"pressure_hpa":1012.3,
//    "gas_kohm":85.2,"gas_baseline_kohm":110.4,"baseline_ready":true,
//    "scent_active":"lavender","scent_detected":true}
#pragma once

#include "ScentController.h"
#include "ScentDetector.h"

namespace xrpod {

// Both return the JSON length, or 0 if it didn't fit in `size`.
size_t buildStateJson(const ScentController &scent, uint32_t uptimeS, char *buf, size_t size);
size_t buildReadingJson(const IaqReading &r, const ScentDetector &det, const char *activeScent,
                        char *buf, size_t size);

}  // namespace xrpod
