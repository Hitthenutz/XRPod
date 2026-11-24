#include "IaqMessages.h"

#include <ArduinoJson.h>
#include <string.h>

namespace xrpod {

static float round1(float v) {
  if (isnan(v) || isinf(v)) return 0;
  return roundf(v * 10.0f) / 10.0f;
}

size_t buildReadingJson(const IaqReading &r, const ScentDetector &det, const char *activeScent,
                        char *buf, size_t size) {
  JsonDocument doc;
  doc["temp_c"] = round1(r.tempC);
  doc["humidity_pct"] = round1(r.humidityPct);
  doc["pressure_hpa"] = round1(r.pressureHpa);
  doc["gas_kohm"] = round1(r.gasOhms / 1000.0f);
  doc["gas_baseline_kohm"] = round1(det.baselineOhms() / 1000.0f);
  doc["baseline_ready"] = det.ready();
  doc["scent_active"] = activeScent != nullptr && activeScent[0] != '\0' ? activeScent : "none";
  doc["scent_detected"] = det.detected();
  if (measureJson(doc) + 1 > size) return 0;
  return serializeJson(doc, buf, size);
}

bool parseActiveScent(const char *json, size_t len, char *out, size_t outSize) {
  if (json == nullptr || out == nullptr || outSize == 0) return false;
  JsonDocument doc;
  if (deserializeJson(doc, json, len)) return false;
  JsonVariantConst scent = doc["selected_scent"];
  if (!scent.is<const char *>()) return false;
  const char *name = scent.as<const char *>();
  size_t n = strlen(name);
  if (n == 0 || n >= outSize) return false;
  memcpy(out, name, n + 1);
  return true;
}

}  // namespace xrpod
