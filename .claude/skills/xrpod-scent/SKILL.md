---
name: xrpod-scent
description: Rules, layout and verify commands for XRPod's scent / indoor-air-quality (IAQ) subsystem - the ESP32 node with two BME688s and two atomizers (subsystems/iaq/firmware/scent-node), the MQTT scent hub in pi/scent.py, and pi/tools/record.py. Use when changing any of those, the MQTT contract, atomizer or sensor hardware settings, or scent verify/calibration.
---

# XRPod scent / IAQ

Read `subsystems/iaq/docs/DESIGN.md` first: architecture, MQTT contract, fail-safe
rules and the MISSING list. Setup and commands are in `subsystems/iaq/README.md`.
The repo-wide rules in `CLAUDE.md` still apply.

## ---------WHERE THINGS LIVE---------

| What | File |
|---|---|
| Pins, atomizer type, limits, sensor addresses | `subsystems/iaq/firmware/scent-node/include/config.h` |
| Wi-Fi, MQTT, command parsing | `src/main.cpp` |
| Atomizer hardware (the only code that knows `ATOMIZER_TYPE`) | `src/atomizer.cpp`, `power()` / `serviceButton()` |
| BME688 pair (BSEC2) | `src/sensors.cpp` |
| Hub: commands, validation, verify, calibration constants | `pi/scent.py` |
| Training / calibration recorder | `pi/tools/record.py` |
| Broker config, boot service | `pi/mosquitto.conf`, `pi/xrpod.service` |

## ---------RULES---------

- **Thin firmware, smart hub.** Decisions (which scent, strength, pass/fail)
  go in `pi/scent.py`, not the firmware.
- **Hardware stays in `atomizer.cpp`.** MQTT and the hub must not change
  when the atomizer type changes.
- **Keep every fail-safe** in DESIGN.md's table: off at boot, off on MQTT
  drop, `MAX_ON_S` cap, one atomizer at a time, unset pins (`-1`) never
  driven, off flushed on shutdown. Keep the tests that cover them.
- **Validate everything from the network** in `parse_telemetry` /
  `parse_detect` (Pi) and `onMessage` (node). Reject, don't guess.
- **Labeled sections:** group code under `---------NAME---------` comments
  (`//` in C++, `#` in Python).
- **MISSING tags:** anything not real yet gets
  `---------MISSING: WHAT---------` next to an obviously placeholder value
  (`-1` for pins), and a row in DESIGN.md's MISSING table. Remove both
  when it's resolved.
- **Ask before any hardware assumption** that isn't already in DESIGN.md
  (pins, voltages, parts, wiring, placement).
- **Keep it lean:** no new files without a new responsibility, no
  abstractions for one caller.
- **Scent list** lives in `SCENT_ATOMIZERS` + `CLASS_NAMES` (`scent.py`),
  `SCENTS` (`pi/store.py`) and `SCENTS` (`hud/src/lib/podSettings.js`);
  change all of them together.
- **Contract changes** (topics, fields) update `main.cpp`, `scent.py`,
  `record.py`, the tests and DESIGN.md together.
- **`MAX_ON_S`** is in `config.h` and `scent.py`; keep them equal.
- `pi/` stays standard library plus `python3-paho-mqtt`, imported only
  inside `MqttLink.start()` so CI doesn't need it.
- **Never commit `include/secrets.h`** (git-ignored) or MQTT passwords.
- Update DESIGN.md, `subsystems/iaq/README.md` and this file when behavior changes.

## ---------VERIFY EVERY CHANGE---------

All three must pass, and new behavior needs a test.

```bash
# 1. Pi tests (CI runs these). The MQTT end-to-end test runs only where
#    mosquitto + paho-mqtt are installed; otherwise it's skipped.
python3 -m unittest discover -s pi/tests -v

# 2. Firmware: 0 warnings. Also build the other atomizer type:
cd subsystems/iaq/firmware/scent-node
pio run
PLATFORMIO_BUILD_SRC_FLAGS="-Wall -Wextra -DATOMIZER_TYPE=AN6_MOTOR -DATOMIZER_PIN_0=25 -DATOMIZER_PIN_1=26" pio run

# 3. Host atomizer test: every line must end in OK
sh test/host/run.sh                 # or CXX="python -m ziglang c++" sh test/host/run.sh
```

`pio run` needs `include/secrets.h`; copy it from `secrets.example.h`.
If you touch the HUD: `cd hud && npm run build`.
