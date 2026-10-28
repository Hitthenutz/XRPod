#include "sensors.h"

#include <Arduino.h>
#include <Wire.h>
#include <bsec2.h>

#include "config.h"

namespace {

// ---------BSEC CONFIGS---------
// Bosch stock IAQ config: 3.3 V supply, 3 s sample rate (LP), 4-day history.
const uint8_t IAQ_CONFIG[] = {
#include "config/bme688/bme688_sel_33v_3s_4d/bsec_selectivity.txt"
};
// ---------MISSING: AI-STUDIO SCENT CONFIG (placeholder: Bosch's FieldAir_HandSanitizer example)---------
// Replace with the bsec_selectivity.txt that BME AI-Studio exports for our
// scents, trained for a 3.3 V supply. Until then the probabilities mean
// "field air vs hand sanitizer", not our scents.
const uint8_t SCAN_CONFIG[] = {
#include "config/FieldAir_HandSanitizer/bsec_selectivity.txt"
};

bsecSensor IAQ_OUTPUTS[] = {
    BSEC_OUTPUT_IAQ,
    BSEC_OUTPUT_CO2_EQUIVALENT,
    BSEC_OUTPUT_BREATH_VOC_EQUIVALENT,
    BSEC_OUTPUT_SENSOR_HEAT_COMPENSATED_TEMPERATURE,
    BSEC_OUTPUT_SENSOR_HEAT_COMPENSATED_HUMIDITY,
    BSEC_OUTPUT_RAW_PRESSURE,
};
bsecSensor SCAN_OUTPUTS[] = {
    BSEC_OUTPUT_RAW_TEMPERATURE,  BSEC_OUTPUT_RAW_PRESSURE,   BSEC_OUTPUT_RAW_HUMIDITY,
    BSEC_OUTPUT_RAW_GAS,          BSEC_OUTPUT_RAW_GAS_INDEX,  BSEC_OUTPUT_GAS_ESTIMATE_1,
    BSEC_OUTPUT_GAS_ESTIMATE_2,   BSEC_OUTPUT_GAS_ESTIMATE_3, BSEC_OUTPUT_GAS_ESTIMATE_4,
};

// ---------STATE---------
Bsec2 iaqSensor;
Bsec2 scanSensor;
bool iaqOk = false;
bool scanOk = false;
IaqReading iaq = {};
ScanReading scan = {};
void (*scanDone)(const ScanReading &) = nullptr;
uint32_t lastErrorLogMs = 0;

void logStatus(const char *name, Bsec2 &s) {
  Serial.printf("# %s BME688: bsec status %d, sensor status %d\n", name, (int)s.status,
                (int)s.sensor.status);
}

// ---------CALLBACKS (one per sensor; BSEC doesn't say which one called)---------
void onIaq(const bme68xData, const bsecOutputs outputs, const Bsec2) {
  for (uint8_t i = 0; i < outputs.nOutputs; i++) {
    const bsecData &o = outputs.output[i];
    switch (o.sensor_id) {
      case BSEC_OUTPUT_IAQ:
        iaq.iaq = o.signal;
        iaq.iaqAccuracy = o.accuracy;
        break;
      case BSEC_OUTPUT_CO2_EQUIVALENT: iaq.eco2Ppm = o.signal; break;
      case BSEC_OUTPUT_BREATH_VOC_EQUIVALENT: iaq.bvocPpm = o.signal; break;
      case BSEC_OUTPUT_SENSOR_HEAT_COMPENSATED_TEMPERATURE: iaq.tC = o.signal; break;
      case BSEC_OUTPUT_SENSOR_HEAT_COMPENSATED_HUMIDITY: iaq.rh = o.signal; break;
      case BSEC_OUTPUT_RAW_PRESSURE: iaq.pHpa = o.signal / 100.0f; break;  // Pa -> hPa
      default: break;
    }
  }
  iaq.valid = true;
}

void onScan(const bme68xData, const bsecOutputs outputs, const Bsec2) {
  int index = -1;
  float gas = 0;
  for (uint8_t i = 0; i < outputs.nOutputs; i++) {
    const bsecData &o = outputs.output[i];
    switch (o.sensor_id) {
      case BSEC_OUTPUT_RAW_TEMPERATURE: scan.tC = o.signal; break;
      case BSEC_OUTPUT_RAW_HUMIDITY: scan.rh = o.signal; break;
      case BSEC_OUTPUT_RAW_PRESSURE: scan.pHpa = o.signal / 100.0f; break;
      case BSEC_OUTPUT_RAW_GAS: gas = o.signal; break;
      case BSEC_OUTPUT_RAW_GAS_INDEX: index = (int)o.signal; break;
      case BSEC_OUTPUT_GAS_ESTIMATE_1:
      case BSEC_OUTPUT_GAS_ESTIMATE_2:
      case BSEC_OUTPUT_GAS_ESTIMATE_3:
      case BSEC_OUTPUT_GAS_ESTIMATE_4:
        scan.probs[o.sensor_id - BSEC_OUTPUT_GAS_ESTIMATE_1] = o.signal;
        break;
      default: break;
    }
  }
  if (index < 0 || index >= MAX_SCAN_STEPS) return;
  // Step 0 starts a new scan, so the previous one is complete.
  if (index == 0 && scan.steps > 0) {
    if (scanDone) scanDone(scan);
    scan.steps = 0;
  }
  scan.gasOhm[index] = gas;
  if (index + 1 > scan.steps) scan.steps = index + 1;
}

// ---------START-UP---------
bool start(Bsec2 &s, const char *name, uint8_t addr, const uint8_t *config, bsecSensor *outputs,
           uint8_t nOutputs, float rate, bsecCallback cb, float tempOffset) {
  if (!s.begin(addr, Wire) || !s.setConfig(config)) {
    logStatus(name, s);
    return false;
  }
  s.setTemperatureOffset(tempOffset);
  if (!s.updateSubscription(outputs, nOutputs, rate)) {
    logStatus(name, s);
    return false;
  }
  s.attachCallback(cb);
  Serial.printf("# %s BME688 at 0x%02x running\n", name, addr);
  return true;
}

void runOne(Bsec2 &s, const char *name) {
  if (s.run()) return;
  // Errors repeat every loop while a sensor is unplugged; log at most once
  // every 10 s.
  if (millis() - lastErrorLogMs > 10000) {
    lastErrorLogMs = millis();
    logStatus(name, s);
  }
}

}  // namespace

// ---------PUBLIC API---------
void sensorsBegin(void (*onScanDone)(const ScanReading &)) {
  scanDone = onScanDone;
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  iaqOk = start(iaqSensor, "IAQ", IAQ_SENSOR_ADDR, IAQ_CONFIG, IAQ_OUTPUTS,
                sizeof(IAQ_OUTPUTS) / sizeof(IAQ_OUTPUTS[0]), BSEC_SAMPLE_RATE_LP, onIaq,
                TEMP_OFFSET_C);
  scanOk = start(scanSensor, "scan", SCAN_SENSOR_ADDR, SCAN_CONFIG, SCAN_OUTPUTS,
                 sizeof(SCAN_OUTPUTS) / sizeof(SCAN_OUTPUTS[0]), BSEC_SAMPLE_RATE_SCAN, onScan,
                 0.0f);
}

void sensorsRun() {
  if (iaqOk) runOne(iaqSensor, "IAQ");
  if (scanOk) runOne(scanSensor, "scan");
}

const IaqReading &sensorsIaq() { return iaq; }
