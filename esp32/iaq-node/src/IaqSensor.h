// BME688 temperature / humidity / pressure / gas sensor, read without
// blocking (moved here from the scent node's earlier firmware). Finds the
// sensor at whichever of the given I2C addresses answers.
#pragma once

#include <Adafruit_BME680.h>
#include <IaqTypes.h>
#include <Wire.h>

class IaqSensor {
 public:
  IaqSensor() : bme_(&Wire) {}

  bool begin(const uint8_t *addresses, uint8_t count, uint32_t periodMs, uint16_t heaterC,
             uint16_t heaterMs);

  // Returns true when a new reading is in `out`. Never blocks for the gas
  // heater; retries finding the sensor every 10 s if it isn't there.
  bool poll(uint32_t nowMs, xrpod::IaqReading &out);

  bool present() const { return present_; }
  uint8_t address() const { return address_; }

 private:
  bool configure();

  Adafruit_BME680 bme_;
  const uint8_t *addresses_ = nullptr;
  uint8_t count_ = 0;
  uint8_t address_ = 0;
  uint32_t periodMs_ = 3000;
  uint16_t heaterC_ = 320;
  uint16_t heaterMs_ = 150;
  bool present_ = false;
  bool pending_ = false;
  uint32_t readyAtMs_ = 0;
  uint32_t nextStartMs_ = 0;
  uint32_t nextRetryMs_ = 0;
};
