# CLAUDE.md

XRPod is a manual control HUD for a senior design capstone pod. The Raspberry
Pi 5 hosts everything: a Python server (standard library only) serves the HUD
(Vite + React + Tailwind) and its JSON API, stores data in SQLite and drives
the hardware. There's no cloud backend. See README.md for setup and how the
pieces fit together.

## Layout

One folder per subsystem; owners and the MQTT contract are in
`docs/subsystems.md`.

- `hud/`: the HUD (`src/App.jsx`, `src/components/`, `src/hooks/`, `src/lib/`);
  `hud/src/api/pod.js` is the only place that talks to the Pi
- `pi/agent.py`: entry point, starts the web server and control loop
- `pi/web.py`: HTTP server (HUD files from `hud/dist/`, `/api/*`, Server-Sent Events)
- `pi/store.py`: SQLite storage and validation of every settings change
- `pi/hardware.py`: sensors and actuators; `pi/scent.py`: scent machine
- `pi/test_pod.py`: tests, run in CI
- `pi/xrpod.service`: systemd unit for the Pi
- `esp32/<node>/`: one PlatformIO project per ESP32 wireless node
  (`esp32/scent-node/`: scent + IAQ); logic in `lib/`, unit-tested
- `vr/README.md`: the Unity project lives in a separate repo; this explains
  how it connects
- `docs/`: cross-subsystem docs
- `.github/workflows/`: `build.yml` (build check) and `security.yml`

## Commands

```bash
cd hud && npm install && npm run build   # must pass; CI runs it
python3 -m unittest discover -s pi -v    # must pass; CI runs it
python3 pi/agent.py                      # run everything at :8080 (stub hardware)
cd hud && npm run dev                    # HUD hot reload; /api proxied to :8080
```

## Git and commits

- Commit as `Hitthenutz <161002723+Hitthenutz@users.noreply.github.com>`.
  Set it before committing:
  `git config user.name "Hitthenutz" && git config user.email "161002723+Hitthenutz@users.noreply.github.com"`
- No `Co-Authored-By: Claude` trailer on commits.
- Never use the owner's personal email in commits or files.
- Don't push to `main`. Work on a branch and open a PR.
- One subsystem per branch/PR: only change that subsystem's folder (see
  `docs/subsystems.md`). `.github/CODEOWNERS` lists who reviews each folder.
- Keep changes to what was asked. Ask before adding tooling, dependencies or
  refactors nobody asked for.

## Code conventions

- Match the existing style: function components, hooks in `hud/src/hooks/`,
  shared constants in `hud/src/lib/podSettings.js`, `@/` import alias.
- Every settings change in the HUD goes through `applyChanges()` in
  `hud/src/hooks/usePodSettings.js`, so it's saved optimistically. The Pi logs history (one
  row per changed field) in `Store.update_settings()`; don't write settings
  any other way.
- `pi/` stays standard-library Python (plus `RPi.GPIO` on the Pi). Ask
  before adding pip packages.
- Heater and AC must stay mutually exclusive in the HUD, in
  `validate_patch()` (store.py) and in `apply_settings()` (hardware.py).
- If you change a settings field or default, update `SETTINGS_SCHEMA` and
  `DEFAULT_SETTINGS` in `pi/store.py` and `DEFAULT_SETTINGS` in
  `hud/src/lib/podSettings.js`. A new scent also goes in `SCENTS` (store.py),
  `SCENTS` (podSettings.js) and `CARTRIDGE_PINS` (scent.py).

## Security rules

- **Never commit secrets** (API keys, tokens, Wi-Fi passwords, `.env` files)
  or the Pi's database (`pi/*.db`, git-ignored).
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
  together, only one scent cartridge on at a time, and every output off when
  the service stops.
- **Pin GitHub Actions to a full commit SHA**, with the version in a comment
  (`uses: owner/action@<40-char sha> # v1.2.3`), never a tag like `@v4`.
  Tags can be moved to point at new code. Dependabot updates the pins.
- **Don't weaken CI to get green.** Don't disable or skip the checks in
  `build.yml` (build, Pi tests) or `security.yml` (npm audit, dependency
  review, gitleaks, CodeQL); fix the finding. New dependencies must not have
  high/critical vulnerabilities.
