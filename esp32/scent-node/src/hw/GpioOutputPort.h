// Real GPIO backend for ScentController.
#pragma once

#include <Arduino.h>
#include <ScentController.h>

class GpioOutputPort : public xrpod::OutputPort {
 public:
  explicit GpioOutputPort(bool activeLow) : activeLow_(activeLow) {}

  // Call first thing in setup(): set the "off" level, then make it an output,
  // so a pin never glitches on.
  void initOff(uint8_t pin) {
    digitalWrite(pin, level(false));
    pinMode(pin, OUTPUT);
    digitalWrite(pin, level(false));
  }

  void write(uint8_t pin, bool on) override { digitalWrite(pin, level(on)); }

 private:
  uint8_t level(bool on) const { return (on != activeLow_) ? HIGH : LOW; }
  bool activeLow_;
};
