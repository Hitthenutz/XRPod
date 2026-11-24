// Bench console over USB serial: type commands in the PlatformIO Serial
// Monitor to drive the node without the Pi. Type "help" to list them.
//
// Bench commands go through ScentController, so the normal safety rules
// still apply (one scent at a time, clamped intensity). A Pi command over MQTT
// always wins and cancels whatever the bench was doing.
#pragma once

#include <Arduino.h>
#include <BenchCommand.h>
#include <ScentController.h>
#include <ScentDetector.h>

#include "hw/GpioOutputPort.h"
#include "hw/IaqSensor.h"
#include "net/MqttLink.h"

class BenchConsole {
 public:
  struct Deps {
    xrpod::ScentController &scent;
    GpioOutputPort &outputs;
    const xrpod::ScentSlot *slots;
    uint8_t numSlots;
    uint8_t diffusersPerSlot;
    xrpod::ScentDetector &detector;
    IaqSensor &iaq;
    MqttLink &link;
    bool networkEnabled;  // false when there is no secrets.h
  };

  explicit BenchConsole(const Deps &d) : d_(d) {}

  void begin();
  void loop(uint32_t nowMs);                      // call every loop()
  void onReading(const xrpod::IaqReading &r);     // call with each new reading
  void cancel(const char *why);                   // stop bench hold / pin pulse
  bool busy() const { return holding_ || pulsing_; }  // bench is driving outputs

 private:
  void handle(const xrpod::BenchCommand &c, uint32_t nowMs);
  void printHelp();
  void printStatus();
  void printSensor();
  void printScan();
  void endPulse();

  Deps d_;
  char line_[65] = {};
  size_t len_ = 0;
  bool overflow_ = false;

  bool holding_ = false;
  xrpod::ScentCommand hold_ = xrpod::kScentOff;
  uint32_t lastHoldMs_ = 0;

  bool pulsing_ = false;
  uint8_t pulsePin_ = 0;
  uint32_t pulseEndMs_ = 0;

  bool log_ = true;
  bool haveReading_ = false;
  xrpod::IaqReading last_ = {0, 0, 0, 0};
};
