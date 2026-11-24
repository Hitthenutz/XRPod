// The JSON this node sends and reads (docs/subsystems.md, MQTT table).
#pragma once

#include "IaqTypes.h"
#include "ScentDetector.h"

namespace xrpod {

// xrpod/iaq/reading, e.g.
//   {"temp_c":22.5,"humidity_pct":41.2,"pressure_hpa":1013.2,"gas_kohm":85.3,
//    "gas_baseline_kohm":90.1,"baseline_ready":true,"scent_active":"lavender",
//    "scent_detected":false}
// Field names match what pi/scent.py reads. Returns the length written, or 0
// if it didn't fit in `size`.
size_t buildReadingJson(const IaqReading &r, const ScentDetector &det, const char *activeScent,
                        char *buf, size_t size);

// The scent the scent node says is running, from its xrpod/scent/state
// message ({"selected_scent":"lavender",...}). Copies the name into `out`
// ("none" when off) and returns true, or returns false and leaves `out` as
// it was if the message isn't a state report.
bool parseActiveScent(const char *json, size_t len, char *out, size_t outSize);

}  // namespace xrpod
