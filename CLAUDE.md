# CLAUDE.md

XRPod is a manual control HUD for a senior design capstone pod. It's a Base44
app (Vite + React + Tailwind) plus a Python agent that runs on the pod's
Raspberry Pi. See README.md for setup, deploy and how the pieces fit together.

## Layout

- `base44/entities/*.jsonc`: data schemas and access rules (RLS)
- `base44/functions/push-sensor-reading/`: Deno function the Pi calls
- `src/`: the HUD (`App.jsx`, `components/`, `hooks/`, `lib/`)
- `pi-agent/agent.py`: runs on the Pi 4, stdlib-only, not part of the web build
- `esp32-scent/esp32-scent.ino`: ESP32 scent mixer firmware; the Pi talks to
  it over serial (`MIX`/`OFF`/`PING` → `OK`/`ERR`)
- `.github/workflows/`: `build.yml` (build check) and `security.yml`

## Commands

```bash
npm install
npm run build         # must pass; this is what CI runs
base44 site dev       # local dev against the real backend
base44 entities push  # after editing base44/entities/
base44 deploy --build # full deploy
```

## Git and commits

- Commit as `Hitthenutz <161002723+Hitthenutz@users.noreply.github.com>`.
  Set it before committing:
  `git config user.name "Hitthenutz" && git config user.email "161002723+Hitthenutz@users.noreply.github.com"`
- No `Co-Authored-By: Claude` trailer on commits.
- Never use the owner's personal email in commits or files.
- Don't push to `main`. Work on a branch and open a PR.
- Keep changes to what was asked. Ask before adding tooling, dependencies or
  refactors nobody asked for.

## Code conventions

- Match the existing style: function components, hooks in `src/hooks/`,
  shared constants in `src/lib/podSettings.js`, `@/` import alias.
- Every PodSettings change goes through `applyChanges()` in
  `usePodSettings.js`, so it's saved optimistically and logged to
  SettingsChangeLog (one row per changed field). Don't write to PodSettings
  anywhere else.
- Heater and AC must stay mutually exclusive, both in the HUD and in
  `apply_settings()` on the Pi.
- If you change a PodSettings field or default, update it in all three places:
  `base44/entities/PodSettings.jsonc`, `src/lib/podSettings.js` and
  `DEFAULT_SETTINGS` in `pi-agent/agent.py`. The scent list also lives in
  `SCENTS` in `agent.py` and `SCENT_NAMES` in the ESP32 sketch.

## Security rules

- **Never commit secrets.** No API keys, `PI_AGENT_KEY` values, tokens or
  `.env` files. `PI_AGENT_KEY` lives only in Base44 secrets
  (`base44 secrets set`) and in the Pi's environment. `.env*` and
  `base44/.app.jsonc` are git-ignored; keep them that way.
- **Keep the device auth in `push-sensor-reading`.** It must keep checking
  `x-agent-key` against `PI_AGENT_KEY` with the constant-time compare. It
  must also keep validating input and passing only known fields to
  `asServiceRole`, because service role bypasses all access rules.
- **Don't loosen access rules (RLS) without asking.** Right now there's no
  login, so PodSettings is open to read and update by anyone with the URL.
  That's a known, accepted risk for now. SensorReading and SettingsChangeLog
  are append-only, and delete is admin-only everywhere.
- **Never use `asServiceRole` from the frontend.** It only exists in backend
  functions.
- **The Pi agent must fail safe.** On errors it keeps the last applied state,
  and on exit it turns every output off. Never let a bad value from the
  network drive the hardware: clamp percentages to 0–100 and never run the
  heater and AC together. The ESP32 must keep its no-command watchdog that
  turns every diffuser off.
- **Don't weaken CI to get green.** Don't disable or skip the checks in
  `security.yml` (npm audit, dependency review, gitleaks, CodeQL); fix the
  finding. New dependencies must not have high/critical vulnerabilities.
