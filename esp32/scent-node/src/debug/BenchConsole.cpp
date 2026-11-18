#include "BenchConsole.h"

#include <WiFi.h>

namespace {
constexpr uint32_t kHoldRefreshMs = 2000;  // well inside the 15 s command timeout
constexpr uint32_t kPulseMs = 3000;
bool reached(uint32_t now, uint32_t at) { return static_cast<int32_t>(now - at) >= 0; }
}  // namespace

void BenchConsole::begin() {
  Serial.println("[bench] console ready - type 'help'");
}

void BenchConsole::loop(uint32_t nowMs) {
  // Read typed characters without blocking.
  while (Serial.available() > 0) {
    char ch = static_cast<char>(Serial.read());
    if (ch == '\r' || ch == '\n') {
      if (overflow_) {
        Serial.println("[bench] line too long (max 64 chars)");
      } else if (len_ > 0) {
        line_[len_] = '\0';
        Serial.printf("> %s\n", line_);
        handle(xrpod::parseBenchLine(line_, d_.slots, d_.numSlots, d_.diffusersPerSlot), nowMs);
      }
      len_ = 0;
      overflow_ = false;
    } else if (len_ < sizeof(line_) - 1) {
      line_[len_++] = ch;
    } else {
      overflow_ = true;
    }
  }

  // Keep a bench scent alive (the controller turns off after 15 s of silence).
  if (holding_ && nowMs - lastHoldMs_ >= kHoldRefreshMs) {
    lastHoldMs_ = nowMs;
    d_.scent.apply(hold_, nowMs);
  }

  if (pulsing_ && reached(nowMs, pulseEndMs_)) {
    endPulse();
    Serial.println("[bench] pin pulse done");
  }
}

void BenchConsole::cancel(const char *why) {
  if (!holding_ && !pulsing_) return;
  holding_ = false;
  endPulse();
  Serial.printf("[bench] cancelled: %s\n", why);
}

void BenchConsole::endPulse() {
  if (!pulsing_) return;
  d_.outputs.write(pulsePin_, false);
  pulsing_ = false;
}

void BenchConsole::onReading(const xrpod::IaqReading &r) {
  last_ = r;
  haveReading_ = true;
  if (log_) {
    Serial.printf("[iaq] %.1f C  %.1f %%RH  %.1f hPa  gas %.1f kOhm  base %.1f%s  detected=%s\n",
                  r.tempC, r.humidityPct, r.pressureHpa, r.gasOhms / 1000.0f,
                  d_.detector.baselineOhms() / 1000.0f, d_.detector.ready() ? "" : " (warming up)",
                  d_.detector.detected() ? "yes" : "no");
  }
}

void BenchConsole::handle(const xrpod::BenchCommand &c, uint32_t nowMs) {
  using xrpod::BenchAction;
  switch (c.action) {
    case BenchAction::None:
      return;
    case BenchAction::Help:
      printHelp();
      return;
    case BenchAction::Status:
      printStatus();
      return;
    case BenchAction::Sensor:
      printSensor();
      return;
    case BenchAction::Net:
      d_.link.printNetStatus();
      return;
    case BenchAction::Scan:
      printScan();
      return;
    case BenchAction::Log:
      log_ = c.flag;
      Serial.printf("[bench] sensor log %s\n", log_ ? "on" : "off");
      return;
    case BenchAction::Off:
      holding_ = false;
      endPulse();
      d_.scent.off(xrpod::Reason::Command);
      Serial.println("[bench] all off");
      return;
    case BenchAction::Scent:
      endPulse();
      hold_.slot = c.slot;
      hold_.intensityPct = c.pct;
      holding_ = true;
      lastHoldMs_ = nowMs;
      d_.scent.apply(hold_, nowMs);
      Serial.printf("[bench] %s at %u%% (held until 'off'; a Pi command overrides)\n",
                    d_.slots[c.slot].name, c.pct);
      return;
    case BenchAction::Pin: {
      holding_ = false;
      endPulse();
      d_.scent.off(xrpod::Reason::Command);  // nothing else on during the check
      pulsePin_ = d_.slots[c.slot].pins[c.diffuser];
      pulsing_ = true;
      pulseEndMs_ = nowMs + kPulseMs;
      d_.outputs.write(pulsePin_, true);
      Serial.printf("[bench] %s diffuser %u (GPIO %u) on for 3 s\n", d_.slots[c.slot].name,
                    c.diffuser + 1, pulsePin_);
      return;
    }
    case BenchAction::Unknown:
      Serial.println("[bench] unknown command - type 'help'");
      return;
    case BenchAction::BadArgs:
      Serial.println("[bench] bad arguments - type 'help'");
      return;
  }
}

void BenchConsole::printHelp() {
  Serial.println("Commands:");
  Serial.println("  status                 scent, diffusers, Wi-Fi/MQTT, sensor");
  Serial.print("  scent <name> <0-100>   run a scent. Names:");
  for (uint8_t i = 0; i < d_.numSlots; ++i) Serial.printf(" %s", d_.slots[i].name);
  Serial.println();
  Serial.println("  off                    everything off");
  Serial.printf("  pin <name> <1-%u>       pulse one diffuser for 3 s (wiring check)\n",
                d_.diffusersPerSlot);
  Serial.println("  net                    Wi-Fi + MQTT connection details");
  Serial.println("  scan                   Wi-Fi networks the ESP32 can see");
  Serial.println("  sensor                 latest BME688 reading");
  Serial.println("  log on|off             print every sensor reading");
}

void BenchConsole::printStatus() {
  Serial.printf("scent    : %s %u%%  reason=%s%s\n", d_.scent.activeName(), d_.scent.intensityPct(),
                xrpod::reasonName(d_.scent.reason()), holding_ ? "  [bench hold]" : "");
  Serial.print("diffusers:");
  for (uint8_t i = 0; i < d_.diffusersPerSlot; ++i) {
    Serial.printf(" %c=%s", 'A' + i, d_.scent.diffuserOn(i) ? "on" : "off");
  }
  Serial.println(pulsing_ ? "  [pin pulse]" : "");
  d_.link.printNetStatus();
  Serial.printf("sensor   : %s, baseline %s\n", d_.iaq.present() ? "BME688 found" : "NOT FOUND",
                d_.detector.ready() ? "ready" : "warming up");
  Serial.printf("uptime   : %lus, free heap %u bytes\n", (unsigned long)(millis() / 1000),
                (unsigned)ESP.getFreeHeap());
}

void BenchConsole::printScan() {
  Serial.println("[bench] scanning Wi-Fi (takes a few seconds)...");
  int n = WiFi.scanNetworks();
  if (n <= 0) {
    Serial.println("[bench] no networks found");
    return;
  }
  Serial.println("  signal  ch  name   (ESP32 only sees 2.4 GHz - a 5 GHz-only network won't show)");
  for (int i = 0; i < n; ++i) {
    Serial.printf("  %4d    %2d  %s\n", WiFi.RSSI(i), WiFi.channel(i), WiFi.SSID(i).c_str());
  }
  WiFi.scanDelete();
}

void BenchConsole::printSensor() {
  if (!haveReading_) {
    Serial.println("[iaq] no reading yet");
    return;
  }
  bool saved = log_;
  log_ = true;
  onReading(last_);
  log_ = saved;
}
