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
platformio.ini            # esp32dev (default), esp32dev-debug (JTAG), native (PC tests)
include/
├── config.h              # pins, timing, topics  <- edit for your wiring
└── secrets.example.h     # copy to secrets.h (git-ignored) with Wi-Fi + broker
lib/scent_core/src/       # pure C++ logic, no Arduino - unit tested
├── ScentTypes.h          # ScentSlot, ScentCommand, IaqReading, clampPct()
├── CommandParser.*       # JSON command -> ScentCommand (never trusts input)
├── ScentController.*     # one scent at a time, duty-cycle intensity, timeouts
├── ScentDetector.*       # gas-resistance drop vs. clean-air baseline
├── Messages.*            # state / reading JSON
└── BenchCommand.*        # bench console command parsing
src/
├── main.cpp              # wires hardware + network to scent_core
├── debug/BenchConsole.*  # USB serial test commands
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

## Safety rules (match pi/scent.py)

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

## Test and debug

> **Right now `src/main.cpp` is the rev A carrier bench test**, not the
> `ScentController` firmware below. It takes `?`, `k1`/`k0` (master power on
> GPIO 16), `p25 [n]` (press a module button), `c25`/`i25`/`o25`
> (continuous/intermittent/off), `h25`/`l25`, `x` and `s`, over USB serial or
> MQTT (`xrpod/test/cmd`, replies on `xrpod/test/reply`). The Pi talks on
> `xrpod/scent/*`, so the HUD can't drive scents until the real firmware is
> back in `main.cpp`.

Three levels, fastest first:

1. **Unit tests on your PC** (no board): `pio test -e native` runs the
   logic in `lib/scent_core`. Needs MinGW-w64 g++ on Windows.
2. **Bench console over USB** (board, no Pi needed): Upload, open the Serial
   Monitor (plug icon), and type:

   ```
   help                  list commands
   status                scent, diffusers, Wi-Fi/MQTT, sensor, free memory
   net                   Wi-Fi, broker address, why MQTT isn't connecting
   scan                  Wi-Fi networks the ESP32 can see (2.4 GHz only)
   scent lavender 60     run a scent (held until "off"; a Pi command overrides)
   off                   everything off
   pin pine 2            pulse one diffuser for 3 s - checks each MOSFET/wire
   sensor                latest BME688 reading
   log off               stop printing every reading
   ```

   Bench commands still go through `ScentController`, so the safety rules
   apply. Crashes print a decoded backtrace (file and line) thanks to the
   `esp32_exception_decoder` monitor filter.
3. **Step-through debugging** (like STM32CubeIDE): the WROOM-32 DevKit has no
   built-in debugger, so you need an **ESP-Prog** (or another FT2232H JTAG
   probe). Wire it to GPIO12 (TDI), 13 (TCK), 14 (TMS), 15 (TDO), GND, and
   3.3 V sense; this firmware keeps those pins free. Pick `esp32dev-debug` in
   the bottom bar's environment selector, set breakpoints, and press F5.

Build / upload buttons in the VS Code bottom bar: check mark = Build,
arrow = Upload (hold BOOT if it sits on "Connecting..."), plug = Serial Monitor.

## Wiring

Pin map, MOSFET wiring, power and reserved pins: [docs/PINOUT.md](docs/PINOUT.md).

## Wiring TODOs

- Confirm the Starry modules mist when powered; if they need a button press,
  drive the button instead of the power.
- 10k pull-down on each MOSFET gate.
- Match the scent names in `config.h` to `SCENTS` in `pi/store.py`.
