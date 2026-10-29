# XRPod scent / IAQ ESP32 node

Firmware for the ESP32 WROOM-32 (Type-C) that runs the scent module: 3 scents
x 2 ultrasonic diffusers, plus a BME688 for temperature, humidity, pressure and
VOC (gas) readings. It talks to the Raspberry Pi 5 over MQTT; the Pi is the
broker.

```
Pi (Mosquitto) --xrpod/scent/cmd---------------> ESP32 --> 6 MOSFETs --> diffusers
               <--xrpod/scent/state (retained)--   |
               <--xrpod/iaq/reading-------------   +-- BME688 (I2C)
               <--xrpod/scent/node  (online/offline, last will)
               <--xrpod/scent/error
```

## Layout

```
platformio.ini            # esp32dev (default) + native (PC unit tests)
include/
├── config.h              # pins, timing, topics  <- edit for your wiring
└── secrets.example.h     # copy to secrets.h (git-ignored) with Wi-Fi + broker
lib/scent_core/src/       # pure C++ logic, no Arduino - unit tested
├── ScentTypes.h          # ScentSlot, ScentCommand, IaqReading, clampPct()
├── CommandParser.*       # JSON command -> ScentCommand (never trusts input)
├── ScentController.*     # one scent at a time, duty-cycle intensity, timeouts
├── ScentDetector.*       # gas-resistance drop vs. clean-air baseline
└── Messages.*            # state / reading JSON
src/
├── main.cpp              # wires hardware + network to scent_core
├── hw/GpioOutputPort.h   # MOSFET outputs
├── hw/IaqSensor.*        # BME688, non-blocking reads
└── net/MqttLink.*        # Wi-Fi + MQTT with retry and last-will
test/test_core/           # Unity tests for lib/scent_core
```

Put new hardware-free logic in `lib/scent_core` with a test; keep `src/` thin.

## Commands from the Pi

Same field names as the Pi's settings, so `hardware.py` can forward them:

```json
{"selected_scent": "lavender", "scent_intensity_pct": 60}
{"selected_scent": "none"}
```

**The Pi must resend the command at least every 15 s** (its 2 s control loop
is fine). If it stops, the node turns everything off.

## Safety rules (match pi-agent/scent.py)

- Only one scent is ever on; switching turns the old one off first.
- Intensity is clamped 0-100; unknown scents, strings, booleans, null mean off.
- Everything off at boot, on bad config, on command timeout, and when MQTT drops.
- Malformed messages are ignored and reported on `xrpod/scent/error`.

## Intensity

Ultrasonic atomizers are on/off, so intensity is a 10 s duty cycle. With two
diffusers per scent, 0-50 % ramps diffuser A and 50-100 % adds diffuser B
(e.g. 30 % = A on 6 s of every 10; 75 % = A always on, B on 5 s of 10).

## Scent detection

`scent_detected` in readings is a first-pass heuristic: the BME688 gas
resistance drops 25 % below its clean-air baseline for 2 readings in a row.
The sensor needs a few minutes to warm up (`baseline_ready`), and humidity
affects it too. Upgrade to Bosch BSEC2 for proper IAQ / bVOC values later.

## Build, upload, test

- VS Code bottom bar: check mark = Build, arrow = Upload, plug = Serial Monitor.
  If upload sits on "Connecting...", hold the board's BOOT button.
- Unit tests on a PC: `pio test -e native` (needs MinGW-w64 g++ on Windows).

## Wiring TODOs

- Confirm the Starry modules mist when powered; if they need a button press,
  drive the button instead of the power.
- 10k pull-down on each MOSFET gate.
- Match the scent names in `config.h` to `SCENTS` in `pi-agent/store.py`.
