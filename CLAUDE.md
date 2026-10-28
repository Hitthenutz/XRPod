# CLAUDE.md

XRPod is a manual control HUD for a senior design capstone pod. The Raspberry
Pi 5 hosts everything: a Python server (standard library only) serves the HUD
(Vite + React + Tailwind) and its JSON API, stores data in SQLite and drives
the hardware. An ESP32 scent / IAQ node (two BME688s, two atomizers) talks
to it over MQTT. There's no cloud backend. A Unity VR scene talks to the
same API. See README.md for setup and how the pieces fit together.

## Layout

- `hud/`: the HUD and its npm project (`package.json`, `vite.config.js`)
  - `hud/src/`: `App.jsx`, `components/`, `hooks/`, `lib/`;
    `hud/src/api/pod.js` is the only place that talks to the Pi
- `pi/`: the Pi controller (standard-library Python)
  - `agent.py`: entry point, starts the web server and control loop
  - `web.py`: HTTP server (HUD files from `hud/dist`, `/api/*`, Server-Sent Events)
  - `store.py`: SQLite storage and validation of every settings change
  - `hardware.py`: sensors and actuators; `scent.py`: scent hub (MQTT to
    the scent / IAQ node)
  - `tools/record.py`: records node data to CSV for training/calibration
  - `tests/`: tests, run in CI
  - `xrpod.service`: systemd unit for the Pi; `mosquitto.conf`: broker
- `subsystems/`: one folder per pod subsystem, each owning its ESP32
  firmware (`firmware/`), docs (`docs/`) and a README. Layout rules:
  `subsystems/README.md`.
  - `iaq/`: the scent / IAQ node. `firmware/scent-node/` is its PlatformIO
    project, and `docs/DESIGN.md` has the MQTT contract and the MISSING
    hardware list. Rules and verify commands:
    `.claude/skills/xrpod-scent/SKILL.md`.
  - `thermal/` (heater, AC) and `airflow/` (fan): placeholders until their
    owners add firmware.
- `unity/`: the Unity VR project root (`Assets/`, `Packages/`,
  `ProjectSettings/`). Own scripts and assets go under `unity/Assets/XRPod/`;
  Pi API client code in `unity/Assets/XRPod/Scripts/PodLink/`. See
  `unity/README.md`.
- `.github/workflows/`: `build.yml` (HUD build, Pi tests, repo size check)
  and `security.yml`

## Commands

```bash
cd hud && npm install                       # HUD commands run from hud/
cd hud && npm run build                     # must pass; CI runs it
python3 -m unittest discover -s pi/tests -v # must pass; CI runs it
python3 pi/agent.py                         # run everything at :8080 (stub hardware)
cd hud && npm run dev                       # HUD hot reload; /api proxied to :8080
cd subsystems/iaq/firmware/scent-node && pio run       # node firmware: must be 0 warnings
cd subsystems/iaq/firmware/scent-node && sh test/host/run.sh  # atomizer host test
```

## Git and commits

- Commit as `Hitthenutz <161002723+Hitthenutz@users.noreply.github.com>`.
  Set it before committing:
  `git config user.name "Hitthenutz" && git config user.email "161002723+Hitthenutz@users.noreply.github.com"`
- No `Co-Authored-By: Claude` trailer or Claude session links in commits,
  PR text or files. Claude must not show up as a contributor.
- Never use the owner's personal email in commits or files.
- Don't push to `main`. Commit and push to a feature branch; the owner opens
  and merges PRs themselves. Don't open PRs unless asked.
- Keep changes to what was asked. Ask before adding tooling, dependencies or
  refactors nobody asked for.

## Code conventions

- Match the existing style: function components, hooks in `hud/src/hooks/`,
  shared constants in `hud/src/lib/podSettings.js`, `@/` import alias
  (points at `hud/src/`). Styling is plain Tailwind 4 classes; there's no
  Tailwind config file or component library.
- Every settings change in the HUD goes through `applyChanges()` in
  `usePodSettings.js`, so it's saved optimistically. The Pi logs history (one
  row per changed field) in `Store.update_settings()`; don't write settings
  any other way.
- `pi/` stays standard-library Python, plus `RPi.GPIO` and
  `python3-paho-mqtt` (both apt) on the Pi. paho is imported only inside
  `MqttLink.start()`, so CI and laptops don't need it. Ask before adding
  pip packages.
- Heater and AC must stay mutually exclusive in the HUD, in
  `validate_patch()` (store.py) and in `apply_settings()` (hardware.py).
- If you change a settings field or default, update `SETTINGS_SCHEMA` and
  `DEFAULT_SETTINGS` in `pi/store.py` and `DEFAULT_SETTINGS` in
  `hud/src/lib/podSettings.js`, and any Unity code that reads or sends it.
  A new scent also goes in `SCENTS` (store.py), `SCENTS` (podSettings.js)
  and `SCENT_ATOMIZERS` + `CLASS_NAMES` (scent.py), and needs an atomizer
  on the node.
- Unity talks to the Pi only through the HTTP API in `pi/web.py`; no other
  channel to the hardware. Keep the API table in README.md current.

## Unity

- Binary assets (models, textures, audio, …) under `unity/` go through Git
  LFS; the rules are in `.gitattributes`. Add a rule there for any new
  binary type. CI fails on files over 2 MB that aren't in LFS.
- Never commit `unity/Library/`, `Temp/`, `Logs/`, `UserSettings/` or builds
  (`unity/.gitignore`). Commit every asset together with its `.meta` file.
- Scenes and prefabs use Force Text serialization so they diff as text.
- When the first C# scripts land, add `csharp` (with `build-mode: none`) to
  the CodeQL matrix in `security.yml`.

## Security rules

- **Never commit secrets** (API keys, tokens, Wi-Fi or MQTT passwords,
  `.env` files, the node's `include/secrets.h`) or the Pi's database
  (`pi/*.db`, git-ignored). MQTT logins on the Pi live in
  `/etc/xrpod.env` and `/etc/mosquitto/xrpod.passwd`, never in the repo.
- **The MQTT broker needs a login** (`allow_anonymous false` in
  `pi/mosquitto.conf`). Anyone who can publish to `xrpod/scent/+/cmd` can
  run the atomizers.
- **The HUD is LAN-only with no login.** Anyone on the pod's Wi-Fi can change
  settings; that's a known, accepted risk for now. Don't expose it to the
  internet (no port forwarding); remote access should go through something
  like Tailscale. Ask before adding auth or changing this.
- **Keep the web server's protections** in `web.py`: writes must be JSON with
  a size limit, a browser `Origin` must match `Host` (CSRF), and static files
  are only served from inside `hud/dist/`. Keep the matching tests.
- **Validate everything on the Pi.** Every write goes through
  `validate_patch()`; reject unknown fields and out-of-range values rather
  than clamping them silently.
- **The Pi must fail safe.** Never let a bad value drive the hardware: clamp
  percentages to 0–100 in `hardware.py`, never run the heater and AC
  together, only one atomizer on at a time, and every output off when the
  service stops. The scent node keeps its own fail-safes (off at boot, off
  when MQTT drops, every command capped at `MAX_ON_S`); see
  `subsystems/iaq/docs/DESIGN.md`.
- **Pin GitHub Actions to a full commit SHA**, with the version in a comment
  (`uses: owner/action@<40-char sha> # v1.2.3`), never a tag like `@v4`.
  Tags can be moved to point at new code. Dependabot updates the pins.
- **Don't weaken CI to get green.** Don't disable or skip the checks in
  `build.yml` (HUD build, Pi tests, repo size) or `security.yml` (npm audit, dependency
  review, gitleaks, CodeQL); fix the finding. New dependencies must not have
  high/critical vulnerabilities.
