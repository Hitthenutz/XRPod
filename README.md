# XRPod

Manual control HUD for the XRPod senior design capstone pod. A Base44 web app
(Vite + React + Tailwind, from the Base44 `backend-and-client` template) plus a
small Python agent that runs on the pod's Raspberry Pi.

```
 phone / tablet / laptop                 Base44                         Raspberry Pi
 ┌──────────────────┐  writes   ┌───────────────────────┐   reads   ┌──────────────────┐
 │  HUD (this site) │ ────────▶ │ PodSettings (1 record)│ ◀──────── │ pi-agent/agent.py│
 │                  │ ◀──────── │ SensorReading         │ ◀──────── │  (x-agent-key)   │
 └──────────────────┘ subscribe │ SettingsChangeLog     │  push-sensor-reading function
                                └───────────────────────┘
```

## Structure

```
base44/
├── config.jsonc                       # Project + site settings
├── entities/
│   ├── PodSettings.jsonc              # Desired state: HUD writes, Pi reads
│   ├── SensorReading.jsonc            # Actual readings pushed by the Pi
│   └── SettingsChangeLog.jsonc        # One row per settings field change
└── functions/
    └── push-sensor-reading/           # Pi → backend, guarded by PI_AGENT_KEY
src/
├── App.jsx                            # The HUD dashboard
├── components/                        # Readouts, cards, history panel, UI bits
├── hooks/                             # usePodSettings, useLatestReading, useChangeLog
└── lib/                               # Field defaults/labels, relative time
public/                                # PWA manifest + home-screen icons
pi-agent/agent.py                      # Runs on the Pi (not part of the web build)
```

## How it works

- **PodSettings** is a single record holding the desired state (target temp and
  humidity, fan speed, heater/AC, scent). Every HUD control writes straight to
  it on change — the UI updates immediately and saves in the background, with
  no save button. Sliders save when you let go, so a drag is one write. Heater
  and AC are mutually exclusive. If two records ever exist, the oldest one is
  canonical (both the HUD and the Pi use that rule).
- **SettingsChangeLog** gets one record per changed field (old → new value).
  Turning the heater on while the AC is on logs two rows: `heater_on` and
  `ac_on`. The **History** panel shows the latest 50, live.
- **SensorReading** rows are pushed by the Pi through the
  `push-sensor-reading` function. The top of the HUD shows the latest one live
  and flags it as stale if the Pi hasn't reported in a minute.
- Access rules: no login yet, so anyone can read/create (and update
  PodSettings). Readings and log rows can't be edited. Only admins can delete
  anything.

## Setup

Requires Node.js 20.19+ and the Base44 CLI (`npm install -g base44`, or prefix
the commands below with `npx`).

```bash
npm install
base44 login
base44 link --create --name XRPod   # first time only; writes base44/.app.jsonc (git-ignored)
```

To link to an app a teammate already created, run `base44 link` and pick it.

### Push the entities

```bash
base44 entities push
```

Run this again whenever you edit a file in `base44/entities/`.

### Set the Pi's shared secret

The Pi is a device, not a logged-in user, so `push-sensor-reading` checks an
`x-agent-key` header against the `PI_AGENT_KEY` secret instead:

```bash
# generate a long random key and store it as an app secret
KEY=$(openssl rand -hex 32)
base44 secrets set PI_AGENT_KEY=$KEY
echo "$KEY"          # put this same value in the Pi agent's PI_AGENT_KEY
base44 secrets list  # confirm it's there (values aren't shown)
```

To rotate it, set a new value and update the Pi.

### Run locally

```bash
base44 site dev   # runs `npm run dev` with your app id injected
```

This talks to your real Base44 backend. Plain `npm run dev` also works if you
set `VITE_BASE44_APP_ID` in `.env.local`.

## Deploy

```bash
base44 deploy --build
```

This pushes entities, deploys the `push-sensor-reading` function, builds the
site and publishes it. You can also do it in pieces:

```bash
base44 entities push
base44 functions deploy push-sensor-reading
base44 site deploy --build
base44 site open          # open the live site
```

Check the function's logs with `base44 logs --function push-sensor-reading`.

## Raspberry Pi agent

`pi-agent/agent.py` uses only the Python standard library. Copy it to the Pi,
fill in the placeholders described at the top of the file (`APP_DOMAIN`,
`APP_ID`, `PI_AGENT_KEY`, and the real sensor/relay/PWM code), then run:

```bash
APP_DOMAIN=your-app.base44.app APP_ID=your_app_id PI_AGENT_KEY=... python3 agent.py
```

Every 3 seconds it reads the sensors, POSTs to
`https://APP_DOMAIN/functions/push-sensor-reading`, fetches PodSettings, and
applies it to the hardware. Until then the sensor and actuator code is stubbed
with fake values, so you can test the whole loop before the hardware is wired.

Quick test of the function from any machine:

```bash
curl -X POST https://your-app.base44.app/functions/push-sensor-reading \
  -H "Content-Type: application/json" -H "x-agent-key: $KEY" \
  -d '{"actual_temp_f": 71.5, "actual_humidity_pct": 44}'
```

## Install on a phone or tablet

The HUD is a Progressive Web App, so there's no app store step. Open the
deployed site and add it to your home screen:

- **iPhone / iPad (Safari):** tap **Share** → **Add to Home Screen**.
- **Android (Chrome):** tap **⋮** → **Add to Home screen** (or **Install app**).
- **Desktop Chrome / Edge:** click the install icon in the address bar.

It opens full-screen with the XRPod icon, like a native app. It still needs a
network connection to reach the pod's backend.
