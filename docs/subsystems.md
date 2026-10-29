# XRPod subsystems

Each subsystem lives in one folder, has one owner, and gets changed through
its own branch and pull request. Shared files (`README.md`, `CLAUDE.md`,
`.github/`, `docs/`) change in their own PRs.

| Folder | Subsystem | Owner | Runs on |
|---|---|---|---|
| `hud/` | Centralized HUD (web app) | Zainab | Browser, served by the Pi |
| `pi/` | Central controller: API, storage, control loop, safety | Team | Raspberry Pi 5 |
| `pi/` → `hardware.py` | Temperature, humidity, airflow (fans, heater, AC) | Genesis | Raspberry Pi 5 |
| `esp32/scent-node/` | Scent + indoor air quality (BME688) | Matt | ESP32 WROOM-32 |
| `vr/` | VR environment link (Unity repo is separate) | VR owner | Meta headsets |
| (planned) | Data logging, VR-independent operation | Maryam | Pi |
| (planned) | Automatic control + AI integration | Salma | Pi |

Fail-safe operation is everyone's job: every subsystem turns its outputs off
when it loses contact with the controller.

## Branch names

`<subsystem>-<topic>`, e.g. `scent-esp32`, `hud-history-panel`,
`pi-fan-pwm`. Open the PR into `main`; the folder's owner reviews it.

## Adding an ESP32 node

1. Copy `esp32/scent-node/` to `esp32/<name>-node/` and strip it down.
2. Keep hardware-free logic in `lib/` with unit tests (`pio test -e native`).
3. Use the MQTT layout below and add your topics to this file.
4. Add your folder and GitHub username to `.github/CODEOWNERS`.

## MQTT (Pi is the broker)

| Topic | Direction | Payload |
|---|---|---|
| `xrpod/scent/cmd` | Pi → node | `{"selected_scent":"lavender","scent_intensity_pct":60}`; resend at least every 15 s |
| `xrpod/scent/state` | node → Pi (retained) | `{"selected_scent","scent_intensity_pct","diffusers":[..],"reason","uptime_s"}` |
| `xrpod/scent/node` | node → Pi (retained, last will) | `online` / `offline` |
| `xrpod/scent/error` | node → Pi | `{"error":"bad_json"}` etc. |
| `xrpod/iaq/reading` | node → Pi | `{"temp_c","humidity_pct","pressure_hpa","gas_kohm","gas_baseline_kohm","baseline_ready","scent_active","scent_detected"}` |

Pattern for new nodes: `xrpod/<subsystem>/cmd`, `/state`, `/node`, `/error`.
Field names match the Pi's settings (`pi/store.py`) so the Pi can forward
them without translating.
