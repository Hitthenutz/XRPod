#include "Messages.h"

#include <ArduinoJson.h>

namespace xrpod {

static float round1(float v) { return roundf(v * 10.0f) / 10.0f; }

static size_t finish(const JsonDocument &doc, char *buf, size_t size) {
  if (buf == nullptr || size == 0 || doc.overflowed()) return 0;
  if (measureJson(doc) + 1 > size) {  // +1 for the terminating NUL
    buf[0] = '\0';
    return 0;
  }
  return serializeJson(doc, buf, size);
}

size_t buildStateJson(const ScentController &scent, uint32_t uptimeS, char *buf, size_t size) {
  JsonDocument doc;
  doc["selected_scent"] = scent.activeName();
  doc["scent_intensity_pct"] = scent.intensityPct();
  JsonArray diffusers = doc["diffusers"].to<JsonArray>();
  for (uint8_t d = 0; d < scent.diffusersPerSlot(); ++d) diffusers.add(scent.diffuserOn(d));
  doc["reason"] = reasonName(scent.reason());
  doc["uptime_s"] = uptimeS;
  return finish(doc, buf, size);
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
  doc["scent_active"] = activeScent != nullptr ? activeScent : "none";
  doc["scent_detected"] = det.detected();
  return finish(doc, buf, size);
}

}  // namespace xrpod
