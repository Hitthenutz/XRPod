# Subsystems

One folder per pod subsystem. Each team member works in their own folder.

| Folder | Subsystem | Pi side today | HUD card |
|---|---|---|---|
| [`iaq/`](iaq/README.md) | Scent / indoor air quality | `pi/scent.py` | `ScentCard.jsx`, `ReadoutsPanel.jsx` |
| [`thermal/`](thermal/README.md) | Heater and AC | stubs in `pi/hardware.py` | `TemperatureCard.jsx` |
| [`airflow/`](airflow/README.md) | Fan | stub in `pi/hardware.py` | `AirflowCard.jsx` |

## What goes in a subsystem folder

```
subsystems/<name>/
├── README.md        # what it is, who owns it, how to build/flash/test
├── docs/DESIGN.md   # wiring, MQTT topics, fail-safes, MISSING hardware list
└── firmware/<node>/ # PlatformIO project for the ESP32
```

Use `iaq/` as the example to copy.

## What stays shared

These are used by every subsystem, so changes there affect everyone:

- `pi/`: the Pi server. Each subsystem's ESP32 gets one module there that
  talks MQTT to it, like `pi/scent.py`. Every setting is validated in
  `pi/store.py`, and `apply_settings()` in `pi/hardware.py` sends settings
  to every subsystem (the heater/AC interlock lives there).
- `hud/`: the HUD. One card per subsystem in `hud/src/components/`.
- `pi/mosquitto.conf`: the MQTT broker. Each node gets its own login and
  its own topic prefix `xrpod/<subsystem>/<node>/...`.

Adding or changing a setting: see "Code conventions" in `CLAUDE.md`.

## Rules for every node

- Never commit `include/secrets.h` (Wi-Fi and MQTT passwords). Commit a
  `secrets.example.h` instead.
- Fail safe: every output off at boot and when MQTT drops, and every
  command expires unless the Pi renews it.
- `pio run` must finish with 0 warnings.
