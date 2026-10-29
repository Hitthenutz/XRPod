// Drives the diffusers. Same safety rules as pi-agent/scent.py:
//   * only one scent cartridge is ever on (break before make),
//   * intensity is clamped 0-100 and anything invalid means off,
//   * off() turns every output off.
// Plus node-only rules:
//   * if the Pi stops sending commands for commandTimeoutMs, turn off,
//   * the caller turns it off when MQTT drops (see main.cpp).
//
// Intensity: ultrasonic atomizers are on/off devices, so intensity is a slow
// time-proportional duty cycle over dutyWindowMs (e.g. 60 % of 10 s = 6 s on).
// With 2 diffusers per scent, 0-50 % ramps diffuser A, 50-100 % adds B.
#pragma once

#include "ScentTypes.h"

namespace xrpod {

// Hardware abstraction so the logic can be tested without GPIO.
class OutputPort {
 public:
  virtual ~OutputPort() {}
  virtual void write(uint8_t pin, bool on) = 0;
};

// Why the controller is in its current state (published to the Pi).
enum class Reason : uint8_t { Boot, BadConfig, Command, Switching, CmdTimeout, MqttLost };
const char *reasonName(Reason r);

struct ScentControllerConfig {
  const ScentSlot *slots;
  uint8_t numSlots;
  uint8_t diffusersPerSlot;
  uint32_t dutyWindowMs;
  uint32_t commandTimeoutMs;
};

class ScentController {
 public:
  ScentController(OutputPort &out, const ScentControllerConfig &cfg);

  // Validates the config and drives every output off. Returns false (and
  // refuses to turn anything on) if the config is invalid.
  bool begin();

  void apply(const ScentCommand &cmd, uint32_t nowMs);
  void off(Reason reason);
  void tick(uint32_t nowMs);  // call every loop()

  bool ready() const { return ready_; }
  int8_t activeSlot() const { return active_; }
  const char *activeName() const;
  uint8_t intensityPct() const { return intensity_; }
  uint8_t diffusersPerSlot() const { return cfg_.diffusersPerSlot; }
  bool diffuserOn(uint8_t index) const;
  Reason reason() const { return reason_; }
  // Bumps whenever scent/intensity/reason changes, so callers know to publish.
  uint32_t changeCount() const { return changes_; }

 private:
  void writePin(uint8_t slot, uint8_t diffuser, bool on, bool force);

  OutputPort &out_;
  ScentControllerConfig cfg_;
  bool ready_ = false;
  int8_t active_ = kNoScent;
  uint8_t intensity_ = 0;
  uint32_t activeSinceMs_ = 0;
  uint32_t lastCommandMs_ = 0;
  Reason reason_ = Reason::Boot;
  uint32_t changes_ = 0;
  bool pinOn_[kMaxSlots][kMaxDiffusersPerSlot] = {};
};

// Duty (0-100) for diffuser `index` of `count` at a given total intensity.
uint8_t diffuserDutyPct(uint8_t intensityPct, uint8_t index, uint8_t count);

// Whether a diffuser at `dutyPct` is on `elapsedMs` into its cycle.
bool dutyOnAt(uint8_t dutyPct, uint32_t elapsedMs, uint32_t windowMs);

}  // namespace xrpod
