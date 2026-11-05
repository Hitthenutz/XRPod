// BME688 temperature / humidity / pressure / gas sensor, read without blocking.
#pragma once

#include <Adafruit_BME680.h>
#include <ScentTypes.h>
#include <Wire.h>

class IaqSensor {
 public:
  IaqSensor() : bme_(&Wire) {}

  bool begin(uint8_t address, uint32_t periodMs, uint16_t heaterC, uint16_t heaterMs);

  // Returns true when a new reading is in `out`. Never blocks for the gas
  // heater; retries begin() every 10 s if the sensor isn't found.
  bool poll(uint32_t nowMs, xrpod::IaqReading &out);

  bool present() const { return present_; }

 private:
  bool configure();

  Adafruit_BME680 bme_;
  uint8_t address_ = 0x77;
  uint32_t periodMs_ = 3000;
  uint16_t heaterC_ = 320;
  uint16_t heaterMs_ = 150;
  bool present_ = false;
  bool pending_ = false;
  uint32_t readyAtMs_ = 0;
  uint32_t nextStartMs_ = 0;
  uint32_t nextRetryMs_ = 0;
};
