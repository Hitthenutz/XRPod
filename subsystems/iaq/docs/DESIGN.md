# Scent / IAQ subsystem: design

Owner: Matt. Scope set by the sponsor: indoor air quality (IAQ) for the pod
first, plus delivering scents and checking that they arrived.

## Architecture

```
 ESP32 scent node (subsystems/iaq/firmware/scent-node)          Raspberry Pi 5
 ┌──────────────────────────────────────┐            ┌──────────────────────────────────┐
 │ BME688 #1 "IAQ"  ─ BSEC2 IAQ config  │  telemetry │ Mosquitto (pi/mosquitto.conf)    │
 │ BME688 #2 "scan" ─ BSEC2 AI-Studio   │  detect    │        │                         │
 │                    gas-scan config   │ ─────────▶ │ agent.py                         │
 │ atomizer 0, atomizer 1 (MOSFETs)     │ ◀───────── │  └ scent.py  ScentHub            │
 │ Wi-Fi + MQTT (PubSubClient)          │   cmd      │     • commands, refresh          │
 └──────────────────────────────────────┘            │     • verify → xrpod/.../verify  │
                                                     │  └ hardware.read_sensors()       │
                                                     │     → HUD readouts + scent check │
                                                     └──────────────────────────────────┘
```

**Thin firmware, smart hub.** The node reads its sensors, publishes what it
sees, and runs an atomizer only when told. Which scent, how strong, and
whether it worked are decided in Python on the Pi (`pi/scent.py`), where
they're easy to change and test.

**Why two BME688s.** One BME688 can run only one BSEC2 config at a time:
either Bosch's IAQ config (IAQ index, eCO2, bVOC) or an AI-Studio gas-scan
config (scent classes), not both. Bosch's library rejects asking one
instance for both. Both sensors report temperature, humidity and pressure.
The pod uses the IAQ sensor's values, since it's the one mounted away from
the atomizers.

**Why the hub lives in agent.py.** The Pi already runs one controller
(`agent.py`) that owns settings, the HUD and the hardware. The scent hub
replaces the old GPIO cartridge driver in `pi/scent.py` behind the same
`apply()` / `off()` / `close()` interface, so there's one process, one
systemd service, and verify results reach the HUD over the existing
Server-Sent Events stream.

## MQTT contract

Prefix `xrpod/scent/<node>/`, node `scent1` (`NODE_ID` in `config.h`,
`NODE` in `scent.py`). JSON payloads except `status`.

| Topic | Direction | QoS / retain | Payload |
|---|---|---|---|
| `status` | node → hub | 1, retained | `online`, or `offline` (last will) |
| `telemetry` | node → hub | 0, every 3 s | `{"t_c", "rh", "p_hpa", "iaq", "iaq_acc" (0-3), "eco2_ppm", "bvoc_ppm", "atomizer", "duty", "uptime_s"}`. Sensor fields are left out until the IAQ sensor's first reading |
| `detect` | node → hub | 0, once per heater scan (~18 s) | `{"t_c", "rh", "p_hpa", "gas_ohm": [1-10 values, one per heater step], "probs": [4 values 0-1], "atomizer", "duty"}`. The scan sensor's own raw T/RH/P. `probs` are `BSEC_OUTPUT_GAS_ESTIMATE_1..4`, all 0 while BSEC is still collecting |
| `cmd` | hub → node | 1 | `{"atomizer": 0\|1, "duty": 1-100, "on_s": 1-30}` or `{"atomizer": -1}` (all off) |
| `verify` | hub → anyone | 1, retained | `{"status": "pass"\|"fail"\|"pending", "reason", "scent", "duty", "prob", "response", "expected"}`; `{"status": "off"}` once the scent stops |

The hub validates every message (`parse_telemetry`, `parse_detect`): it
rejects wrong types, NaN/inf, negative resistances and probabilities
outside 0-1, and ignores the message. The node rejects a `cmd` that isn't
exactly this shape and keeps its current state.

## Fail-safe

| Rule | Where |
|---|---|
| Atomizers off at boot, before Wi-Fi and sensors start | `setup()` → `atomizerBegin()` |
| Atomizers off whenever Wi-Fi or MQTT isn't connected (Wi-Fi checked too, because a dead socket can look connected until TCP times out) | `loop()` in `main.cpp` |
| Each command runs at most `MAX_ON_S` (30 s); the hub re-sends every `CMD_REFRESH_S` (5 s), so a dead Pi stops the scent within 30 s | `atomizerStart()` + `ScentHub.apply()` |
| At most one atomizer on, break before make | `atomizerStart()` |
| Pins left at `-1` are never driven; a command for one is rejected | `atomizer.cpp` |
| Unknown scent, `none`, 0 % or junk settings mean off | `ScentHub.apply()`, `hardware.to_pct()` |
| Agent stops → "off" is published and flushed before disconnecting | `ScentHub.close()`, `MqttLink.close()` |
| Commands are dropped, not queued, while the hub is disconnected, so nothing stale replays on reconnect. A dropped command is retried on the next 2 s tick | `MqttLink.publish()`, `ScentHub._send()` |
| Broken MQTT (e.g. paho missing) disables scent but keeps the HUD up | `ScentHub.__init__` |
| A quiet node shows "--" in the HUD, never stale or fake numbers | `ScentHub.environment()`, `hardware.read_sensors()` |

## Atomizers

`ATOMIZER_TYPE` in `config.h` picks the hardware at compile time. Only
`power()` / `serviceButton()` in `atomizer.cpp` know the difference;
MQTT and the hub are identical for both.

| | `MIST_MODULE` (default) | `AN6_MOTOR` |
|---|---|---|
| Device | Starry 5 V USB ultrasonic mist module | Airversa AN6 waterless diffuser, battery disconnected |
| Liquid | Water + a few drops of oil | Pure oil |
| Drive | Logic MOSFET switches the module's 5 V | Logic MOSFET + flyback diode across the pump motor |
| Gate signal | Digital on/off | LEDC PWM at 20 kHz, duty = `MOTOR_VOLTS / SUPPLY_VOLTS`, so the motor sees ~3.7 V average from 5 V |
| Button | Optional optocoupler "press" `POWER_SETTLE_MS` after power-up (`ATOMIZER_NEEDS_PRESS`) | None |

**Intensity** (`duty`, the HUD's scent intensity) is time-proportioned on
both types: on for `duty` % of every `PULSE_PERIOD_MS` (10 s). A repeated
command only extends the run, so the hub's refresh doesn't restart the
cycle. With the button press enabled, each pulse lasts at least
`POWER_SETTLE_MS + PRESS_MS` (450 ms), so the press can finish. Without
that floor, duties under ~5 % would never mist. Calibration (MISSING #12)
should check where low duties start to register.

## Verify method

After any change the hub waits `SETTLE_S`, then judges every `detect`:

1. **Right scent:** the probability of the selected scent's class
   (`CLASS_NAMES`) is at least `PASS_PROB`.
2. **Right strength:** `response = 1 - mean(gas_ohm[i] / baseline[i])`.
   Scent VOCs lower a BME688's resistance, so 0 means clean air. It passes
   if it's within `STRENGTH_TOL` of `INTENSITY_PER_DUTY × duty`.
3. The node must report that it's running the commanded atomizer. If it
   isn't (e.g. pins still `-1`, so it rejected the command), the check
   fails with that as the reason, rather than "too weak".
4. The **baseline** is a slow moving average (`BASELINE_ALPHA`) of the
   per-step resistance, learned only while every atomizer has been off for
   at least `SETTLE_S`.

All-zero probabilities mean "pending" (classifier warming up). A missing
baseline, the wrong class, too weak or too strong mean "fail" with a
reason. The node going offline, or sending no scans for `DETECT_FRESH_S`,
also means fail. The HUD shows the result under the scent slider.

## MISSING

Placeholders until the hardware is on the bench. Each is tagged
`---------MISSING: …---------` in the code with an obvious placeholder.

| # | What | Placeholder | Where | How to resolve |
|---|---|---|---|---|
| 1 | Final atomizer choice | `ATOMIZER_TYPE = MIST_MODULE` | `config.h` | Pick Starry vs AN6; set `ATOMIZER_TYPE` |
| 2 | Atomizer MOSFET gate pins | `-1` (never driven) | `config.h` `ATOMIZER_PIN_0/1` | Wire it, then set GPIOs (avoid strapping pins 0, 2, 5, 12, 15 and input-only 34-39) |
| 3 | Does the mist module need a button press | `ATOMIZER_NEEDS_PRESS 0` | `config.h` | Power the module from a switched 5 V; see whether it mists without pressing its button |
| 4 | Optocoupler pins (mist module only) | `-1` | `config.h` `PRESS_PIN_0/1` | Only if #3 says yes |
| 5 | AN6 motor voltage | `MOTOR_VOLTS 3.7` | `config.h` | Measure across the pump motor with the stock battery board running |
| 6 | BME688 I2C addresses (SDO wiring) | scan `0x76`, IAQ `0x77` | `config.h` | SDO to GND = 0x76, to VDDIO = 0x77; check your breakout's jumper |
| 7 | I2C pins | ESP32 defaults SDA 21, SCL 22 | `config.h` | Set once wired |
| 8 | IAQ sensor temperature offset | `TEMP_OFFSET_C 0` | `config.h` | Compare with a reference thermometer in the pod after warm-up |
| 9 | AI-Studio scent config | Bosch's `FieldAir_HandSanitizer` example | `sensors.cpp` | Record with `record.py` / the dev kit, train in BME AI-Studio for a 3.3 V supply, export `bsec_selectivity.txt`, replace the `#include` |
| 10 | AI-Studio class order | `clean_air, lavender, pine, None` | `scent.py` `CLASS_NAMES` | Match the class order in the AI-Studio export |
| 11 | Final scent names | `lavender`, `pine` | `scent.py` `SCENT_ATOMIZERS`, `store.py` `SCENTS`, `podSettings.js` `SCENTS` | Pick the two scents, rename everywhere |
| 12 | Verify calibration | `SETTLE_S 60`, `PASS_PROB 0.6`, `INTENSITY_PER_DUTY 0.004`, `STRENGTH_TOL 0.15` | `scent.py` | Record clean air, then each scent at 25/50/75/100 %; compute the response per duty |
| 13 | AI-Studio import format | `record.py` writes CSV | `pi/tools/record.py` | Check that AI-Studio accepts the CSV. Its native format is the dev kit's `.bmerawdata`, so a converter may be needed |
| 14 | IAQ sensor placement | none | hardware | Mount away from the atomizers' airflow, or every puff reads as bad air |

## Not done yet (software follow-ups)

- **BSEC state persistence.** The IAQ sensor relearns its baseline after
  every reboot (accuracy 0 → 3 over hours). Bosch's `basic_config_state`
  example saves the state to flash.
- **MQTT access control.** The broker needs a login, but the node and the
  hub share full access. An ACL file could limit the node to its own topics.
- **Firmware build and host test in CI.** Currently they're run by hand
  (subsystems/iaq/README.md).
