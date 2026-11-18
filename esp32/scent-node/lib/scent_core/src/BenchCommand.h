// Bench console: commands you type in the PlatformIO Serial Monitor to test
// the node without the Pi. Parsing lives here (no Arduino) so it's unit-tested;
// src/debug/BenchConsole.cpp acts on the result.
//
//   help                      list commands
//   status                    scent state, diffusers, Wi-Fi/MQTT, sensor
//   net                       Wi-Fi, broker address, MQTT connection details
//   scan                      list Wi-Fi networks the ESP32 can see (2.4 GHz)
//   scent <name> <0-100>      run a scent (held until "off" or a Pi command)
//   off                       everything off
//   pin <name> <1|2>          pulse one diffuser for 3 s (wiring check)
//   sensor                    latest BME688 reading + baseline
//   log on|off                print every sensor reading (default on)
#pragma once

#include "ScentTypes.h"

namespace xrpod {

enum class BenchAction : uint8_t {
  None, Help, Status, Net, Scan, Scent, Off, Pin, Sensor, Log, Unknown, BadArgs
};

struct BenchCommand {
  BenchAction action;
  int8_t slot;       // Scent, Pin
  uint8_t pct;       // Scent
  uint8_t diffuser;  // Pin (0-based)
  bool flag;         // Log
};

// Case-insensitive; extra spaces are fine. Empty line -> None.
BenchCommand parseBenchLine(const char *line, const ScentSlot *slots, uint8_t numSlots,
                            uint8_t diffusersPerSlot);

}  // namespace xrpod
