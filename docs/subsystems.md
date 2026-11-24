# XRPod subsystems

Each subsystem lives in one folder, has one owner, and gets changed through
its own branch and pull request. Shared files (`README.md`, `CLAUDE.md`,
`.github/`, `docs/`) change in their own PRs.

| Folder | Subsystem | Owner | Runs on |
|---|---|---|---|
| `hud/` | Centralized HUD (web app) | Zainab | Browser, served by the Pi |
| `pi/` | Central controller: API, storage, control loop, safety | Team | Raspberry Pi 5 |
| `pi/` → `hardware.py` | Temperature, humidity, airflow (fans, heater, AC) | Genesis | Raspberry Pi 5 |
| `esp32/fan-node/` | Fans: speed + RPM | Genesis | ESP32-S3 |
| `esp32/scent-node/` | Scent diffusers | Matt | ESP32 WROOM-32 |
| `esp32/iaq-node/` | Indoor air quality: BME688 temperature, humidity, gas (its own board, so the scent firmware stays as it is) | Maryam, with Matt | ESP32 WROOM-32 |
| `vr/` | VR app (Unity 6.6): environments, zone detection, reports to the Pi | Maryam | Meta Quest 3 |
| (planned) | Data logging, VR-independent operation | Maryam | Pi |
| (planned) | Automatic control + AI integration | Salma | Pi |

Fail-safe operation is everyone's job: every subsystem turns its outputs off
when it loses contact with the controller.

## Branch names

`<subsystem>-<topic>`, e.g. `scent-esp32`, `hud-history-panel`,
`pi-fan-pwm`. Open the PR into `main`; the folder's owner reviews it.

## VR ↔ Pi (HTTP on the pod's Wi-Fi)

| Request | Direction | What |
|---|---|---|
| `GET /api/settings` | headset reads, ~1/s | `selected_environment` (picked in the HUD) |
| `PUT /api/vr/state` | headset → Pi, on change + every ~5 s | environment and `zone_id`; the Pi keeps the latest |
| `GET /api/vr/state`, `vr` event | HUD reads | what the headset last reported |
| `PUT /api/vr/frame` | headset → Pi, ~8/s while connected | live view: a small JPEG of what the user sees, `{"jpeg_base64": "..."}`; kept in memory only |
| `GET /api/vr/frame` | HUD reads | the newest live-view picture, or `204` if none in the last 3 s |

The headset only reports. In auto mode the Pi applies a recipe per
`zone_id` (`vr/docs/ZONES.md`). Details: `vr/docs/POD_PROTOCOL_PROPOSAL.md`.

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
| `xrpod/fan/cmd` | Pi → node | `{"fan_speed_pct":60}`; resend at least every 15 s |
| `xrpod/fan/state` | node → Pi (retained) | `{"fan_speed_pct","fan_rpm","uptime_s"}` |
| `xrpod/fan/node` | node → Pi (retained, last will) | `online` / `offline` |
| `xrpod/fan/error` | node → Pi | `{"error":"bad_json"}` etc. |
| `xrpod/iaq/reading` | IAQ node → Pi, every 3 s | `{"temp_c","humidity_pct","pressure_hpa","gas_kohm","gas_baseline_kohm","baseline_ready","scent_active","scent_detected"}`; the HUD's temperature and humidity come from it while it's fresh |
| `xrpod/iaq/node` | IAQ node → Pi (retained, last will) | `online` / `offline` |

The IAQ node also listens to `xrpod/scent/state`, so scent detection knows
when a scent is meant to be on.

Pattern for new nodes: `xrpod/<subsystem>/cmd`, `/state`, `/node`, `/error`.
Field names match the Pi's settings (`pi/store.py`) so the Pi can forward
them without translating.
