#include "CommandParser.h"

#include <ArduinoJson.h>
#include <string.h>

namespace xrpod {

static int8_t findSlot(const char *name, const ScentSlot *slots, uint8_t numSlots) {
  if (name == nullptr) return kNoScent;
  for (uint8_t i = 0; i < numSlots; ++i) {
    if (slots[i].name != nullptr && strcmp(slots[i].name, name) == 0) {
      return static_cast<int8_t>(i);
    }
  }
  return kNoScent;
}

ParseResult parseScentCommand(const char *payload, size_t len,
                              const ScentSlot *slots, uint8_t numSlots,
                              ScentCommand &out) {
  if (payload == nullptr || len == 0) return ParseResult::BadJson;

  JsonDocument doc;
  if (deserializeJson(doc, payload, len) != DeserializationError::Ok) {
    return ParseResult::BadJson;
  }
  if (!doc.is<JsonObject>()) return ParseResult::NotObject;

  // Booleans are not percentages (to_pct(True) is 0 on the Pi too).
  JsonVariant intensity = doc["scent_intensity_pct"];
  uint8_t pct = 0;
  if (!intensity.is<bool>() && intensity.is<double>()) {
    pct = clampPct(intensity.as<double>());
  }

  const char *name = doc["selected_scent"].is<const char *>()
                         ? doc["selected_scent"].as<const char *>()
                         : nullptr;
  int8_t slot = findSlot(name, slots, numSlots);

  bool isNone = name == nullptr || strcmp(name, "none") == 0;
  if (slot == kNoScent || pct == 0) {
    out = kScentOff;
    return (slot == kNoScent && !isNone) ? ParseResult::UnknownScent : ParseResult::Ok;
  }

  out.slot = slot;
  out.intensityPct = pct;
  return ParseResult::Ok;
}

const char *parseResultName(ParseResult r) {
  switch (r) {
    case ParseResult::Ok: return "ok";
    case ParseResult::UnknownScent: return "unknown_scent";
    case ParseResult::BadJson: return "bad_json";
    case ParseResult::NotObject: return "not_object";
  }
  return "?";
}

}  // namespace xrpod
