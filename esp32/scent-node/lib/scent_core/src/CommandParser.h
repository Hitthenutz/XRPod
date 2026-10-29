// Parses scent commands from the Pi (MQTT topic xrpod/scent/cmd).
//
// Payload uses the same field names as the Pi's settings:
//   {"selected_scent": "lavender", "scent_intensity_pct": 60}
//   {"selected_scent": "none"}
#pragma once

#include "ScentTypes.h"

namespace xrpod {

enum class ParseResult : uint8_t {
  Ok,            // out holds the command (may be "off")
  UnknownScent,  // scent name not configured on this node; out is "off"
  BadJson,       // not valid JSON; out untouched, ignore the message
  NotObject,     // valid JSON but not an object; out untouched
};

// Never trusts the payload: unknown scents, "none", 0 %, and non-numeric
// intensities (strings, booleans, null, NaN) all mean off.
ParseResult parseScentCommand(const char *payload, size_t len,
                              const ScentSlot *slots, uint8_t numSlots,
                              ScentCommand &out);

const char *parseResultName(ParseResult r);

}  // namespace xrpod
