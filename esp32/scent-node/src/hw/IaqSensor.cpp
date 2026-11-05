#include "IaqSensor.h"

#include <Arduino.h>

static bool reached(uint32_t now, uint32_t at) { return static_cast<int32_t>(now - at) >= 0; }

bool IaqSensor::begin(uint8_t address, uint32_t periodMs, uint16_t heaterC, uint16_t heaterMs) {
  address_ = address;
  periodMs_ = periodMs;
  heaterC_ = heaterC;
  heaterMs_ = heaterMs;
  return configure();
}

bool IaqSensor::configure() {
  present_ = bme_.begin(address_);
  pending_ = false;
  if (!present_) return false;
  bme_.setTemperatureOversampling(BME680_OS_8X);
  bme_.setHumidityOversampling(BME680_OS_2X);
  bme_.setPressureOversampling(BME680_OS_4X);
  bme_.setIIRFilterSize(BME680_FILTER_SIZE_3);
  bme_.setGasHeater(heaterC_, heaterMs_);
  return true;
}

bool IaqSensor::poll(uint32_t nowMs, xrpod::IaqReading &out) {
  if (!present_) {
    if (reached(nowMs, nextRetryMs_)) {
      nextRetryMs_ = nowMs + 10000;
      configure();
    }
    return false;
  }

  if (!pending_) {
    if (!reached(nowMs, nextStartMs_)) return false;
    nextStartMs_ = nowMs + periodMs_;
    unsigned long readyAt = bme_.beginReading();
    if (readyAt == 0) {
      present_ = false;  // lost on the bus; retry later
      return false;
    }
    readyAtMs_ = static_cast<uint32_t>(readyAt);
    pending_ = true;
    return false;
  }

  if (!reached(nowMs, readyAtMs_)) return false;
  pending_ = false;
  if (!bme_.endReading()) {
    present_ = false;
    return false;
  }
  out.tempC = bme_.temperature;
  out.humidityPct = bme_.humidity;
  out.pressureHpa = bme_.pressure / 100.0f;
  out.gasOhms = static_cast<float>(bme_.gas_resistance);
  return true;
}
