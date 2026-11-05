#include "ScentController.h"

namespace xrpod {

const char *reasonName(Reason r) {
  switch (r) {
    case Reason::Boot: return "boot";
    case Reason::BadConfig: return "bad_config";
    case Reason::Command: return "command";
    case Reason::Switching: return "switching";
    case Reason::CmdTimeout: return "cmd_timeout";
    case Reason::MqttLost: return "mqtt_lost";
  }
  return "?";
}

uint8_t diffuserDutyPct(uint8_t intensityPct, uint8_t index, uint8_t count) {
  if (count == 0 || index >= count) return 0;
  int32_t v = static_cast<int32_t>(clampPct(intensityPct)) * count - 100 * index;
  if (v <= 0) return 0;
  if (v >= 100) return 100;
  return static_cast<uint8_t>(v);
}

bool dutyOnAt(uint8_t dutyPct, uint32_t elapsedMs, uint32_t windowMs) {
  if (dutyPct == 0 || windowMs == 0) return false;
  if (dutyPct >= 100) return true;
  uint32_t phase = elapsedMs % windowMs;
  uint32_t onMs = static_cast<uint32_t>(static_cast<uint64_t>(windowMs) * dutyPct / 100);
  return phase < onMs;
}

ScentController::ScentController(OutputPort &out, const ScentControllerConfig &cfg)
    : out_(out), cfg_(cfg) {}

bool ScentController::begin() {
  ready_ = cfg_.slots != nullptr && cfg_.numSlots > 0 && cfg_.numSlots <= kMaxSlots &&
           cfg_.diffusersPerSlot > 0 && cfg_.diffusersPerSlot <= kMaxDiffusersPerSlot &&
           cfg_.dutyWindowMs > 0 && cfg_.commandTimeoutMs > 0;
  // Force every pin low even if the config is bad, so nothing is left on.
  if (cfg_.slots != nullptr) {
    uint8_t slots = cfg_.numSlots <= kMaxSlots ? cfg_.numSlots : kMaxSlots;
    uint8_t diffs = cfg_.diffusersPerSlot <= kMaxDiffusersPerSlot ? cfg_.diffusersPerSlot
                                                                 : kMaxDiffusersPerSlot;
    for (uint8_t s = 0; s < slots; ++s) {
      for (uint8_t d = 0; d < diffs; ++d) writePin(s, d, false, true);
    }
  }
  active_ = kNoScent;
  intensity_ = 0;
  reason_ = ready_ ? Reason::Boot : Reason::BadConfig;
  ++changes_;
  return ready_;
}

const char *ScentController::activeName() const {
  return active_ == kNoScent ? "none" : cfg_.slots[active_].name;
}

bool ScentController::diffuserOn(uint8_t index) const {
  if (active_ == kNoScent || index >= cfg_.diffusersPerSlot) return false;
  return pinOn_[active_][index];
}

void ScentController::writePin(uint8_t slot, uint8_t diffuser, bool on, bool force) {
  if (!force && pinOn_[slot][diffuser] == on) return;
  pinOn_[slot][diffuser] = on;
  out_.write(cfg_.slots[slot].pins[diffuser], on);
}

void ScentController::off(Reason reason) {
  if (cfg_.slots != nullptr) {
    for (uint8_t s = 0; s < cfg_.numSlots && s < kMaxSlots; ++s) {
      for (uint8_t d = 0; d < cfg_.diffusersPerSlot && d < kMaxDiffusersPerSlot; ++d) {
        writePin(s, d, false, false);
      }
    }
  }
  if (active_ != kNoScent || reason_ != reason) ++changes_;
  active_ = kNoScent;
  intensity_ = 0;
  reason_ = reason;
}

void ScentController::apply(const ScentCommand &cmd, uint32_t nowMs) {
  if (!ready_) return;
  lastCommandMs_ = nowMs;

  uint8_t pct = clampPct(cmd.intensityPct);
  if (cmd.slot < 0 || cmd.slot >= static_cast<int8_t>(cfg_.numSlots) || pct == 0) {
    off(Reason::Command);
    return;
  }

  bool changed = cmd.slot != active_ || pct != intensity_ || reason_ != Reason::Command;
  if (cmd.slot != active_) {
    // Break before make: everything off first, then start the new cycle.
    off(Reason::Switching);
    active_ = cmd.slot;
    activeSinceMs_ = nowMs;
  }
  intensity_ = pct;
  reason_ = Reason::Command;
  if (changed) ++changes_;
  tick(nowMs);
}

void ScentController::tick(uint32_t nowMs) {
  if (!ready_ || active_ == kNoScent) return;

  if (nowMs - lastCommandMs_ > cfg_.commandTimeoutMs) {
    off(Reason::CmdTimeout);
    return;
  }

  uint32_t elapsed = nowMs - activeSinceMs_;
  // Two passes so an output always turns off before another turns on.
  bool want[kMaxDiffusersPerSlot] = {};
  for (uint8_t d = 0; d < cfg_.diffusersPerSlot; ++d) {
    want[d] = dutyOnAt(diffuserDutyPct(intensity_, d, cfg_.diffusersPerSlot), elapsed,
                       cfg_.dutyWindowMs);
  }
  for (uint8_t s = 0; s < cfg_.numSlots; ++s) {
    for (uint8_t d = 0; d < cfg_.diffusersPerSlot; ++d) {
      bool on = (s == static_cast<uint8_t>(active_)) && want[d];
      if (!on) writePin(s, d, false, false);
    }
  }
  for (uint8_t d = 0; d < cfg_.diffusersPerSlot; ++d) {
    if (want[d]) writePin(static_cast<uint8_t>(active_), d, true, false);
  }
}

}  // namespace xrpod
