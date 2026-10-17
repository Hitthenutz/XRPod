# XRPod

Manual control HUD for the XRPod senior design capstone pod. The Raspberry Pi
5 does everything: it hosts the HUD website, stores the data and drives the
hardware. There are no cloud accounts, no usage limits and no internet
required.

```
 phone / tablet / laptop                        Raspberry Pi 5 (pi/agent.py)
 ┌──────────────────┐   HTTP on the     ┌──────────────────────────────────────────┐
 │  HUD in browser  │ ─ local Wi-Fi ──▶ │ web.py      serves the HUD + JSON API     │
 │  (home screen)   │ ◀─ live events ── │ store.py    settings, readings, history   │
 └──────────────────┘                   │             in SQLite (xrpod.db)         │
                                        │ hardware.py heater, AC, fan, sensors     │
 Unity (VR) ── same API ──────────────▶ │ scent.py    scent machine                │
                                        └──────────────────────────────────────────┘
```

## Structure

```
hud/                     # The HUD website (Vite + React + Tailwind)
├── src/
│   ├── App.jsx          # The dashboard
│   ├── api/pod.js       # Client for the Pi's API + live events
│   ├── components/      # Readouts, cards, history panel, UI bits
│   ├── hooks/           # usePodSettings, useLatestReading, useChangeLog
│   └── lib/             # Field labels, relative time
├── public/              # PWA manifest + home-screen icons
└── package.json         # npm commands run from hud/
pi/                      # Runs on the Raspberry Pi
├── agent.py             # Entry point: starts the web server + control loop
├── web.py               # HTTP server: HUD files, API, live events
├── store.py             # SQLite storage + validation of every change
├── hardware.py          # Sensors and actuators (stubbed until wired up)
├── scent.py             # Scent machine (one cartridge at a time + intensity PWM)
├── tests/               # Tests (run in CI)
└── xrpod.service        # systemd unit: start on boot
unity/                   # The VR project (Unity, assets in Git LFS)
.github/workflows/       # CI: build, tests, security checks
```

## How it works

- **Settings** (target temp and humidity, fan speed, heater/AC, scent) live
  on the Pi. Every HUD control saves straight away; there's no save button.
  The screen updates instantly, and quick changes in a row are merged into
  one save. Sliders save when you let go.
- **The Pi validates every change.** Out-of-range values, unknown fields and
  "heater and AC both on" are rejected. Turning one of heater/AC on turns
  the other off.
- **History:** each changed field gets one row (old → new value, plus the
  device's IP address). The **History** panel shows the latest 50.
- **Live updates:** every 2 seconds the Pi reads the sensors, applies the
  settings to the hardware and pushes the reading to every open HUD. A
  change made on one phone shows up on the others immediately. If the Pi
  restarts or Wi-Fi drops, the HUD reconnects by itself.
- **Storage:** readings older than 24 hours are deleted, and history keeps
  the newest 5,000 changes, so the SD card doesn't fill up.

## Try it on your laptop (no Pi needed)

The hardware is stubbed, so the whole system runs anywhere with Python 3 and
Node.js 20.19+:

```bash
cd hud
npm install
npm run build              # builds the HUD into hud/dist/
cd ..
python3 pi/agent.py        # open http://localhost:8080
```

To work on the HUD with hot reload, keep the agent running and, in a second
terminal, run (from `hud/`):

```bash
npm run dev                # open the URL it prints; /api is forwarded to the agent
POD_URL=http://xrpod.local npm run dev   # …or use the real Pi's data instead
```

Run the Pi tests with `python3 -m unittest discover -s pi/tests -v`.

## Run it on the Pi

1. **Name the Pi `xrpod`** in Raspberry Pi Imager when you flash the SD card,
   or later with `sudo raspi-config` → System Options → Hostname. Phones can
   then reach it at `http://xrpod.local`.
2. **Get the code and build the HUD:**
   ```bash
   git clone https://github.com/Hitthenutz/XRPod.git ~/XRPod
   cd ~/XRPod/hud
   npm install && npm run build
   ```
   Building needs Node.js 20.19 or newer. Raspberry Pi OS's own `nodejs`
   package is older, so install Node 22 from [NodeSource](https://github.com/nodesource/distributions)
   first. Alternatively, skip Node on the Pi: download the **hud-dist**
   artifact from the latest **Build** run on GitHub (Actions tab), or run
   `npm run build` on a laptop, and copy it to `~/XRPod/hud/dist` on the Pi.
3. **Start it on boot:**
   ```bash
   cd ~/XRPod
   sudo cp pi/xrpod.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now xrpod
   journalctl -u xrpod -f     # watch the logs
   ```
   The service runs on port 80. If your Pi username isn't `pi`, edit `User=`
   and the paths in the file first.
4. **Update later** with `cd ~/XRPod && git pull && (cd hud && npm install && npm run build) && sudo systemctl restart xrpod`.

Settings live in `pi/xrpod.db`. Delete it, with the service stopped,
to reset everything to defaults.

### Hardware

Everything is stubbed until you fill in the `TODO(hardware)` parts of
`pi/hardware.py` (heater relay, AC relay, fan PWM, temperature and
humidity sensor) and set the pin numbers at the top of `pi/scent.py`.

Safety rules the Pi enforces no matter what any client sends:

- the heater and AC never run together,
- percentages are clamped to 0–100 and junk values mean off,
- only one scent cartridge is ever on,
- when the service stops, every output turns off.

Bench-test the scent machine on its own:

```bash
cd pi
python3 scent.py lavender 60                         # stub: logs only
SCENT_HARDWARE=gpio python3 scent.py lavender 60 10  # real pins for 10 s
```

Then uncomment `SCENT_HARDWARE=gpio` in `pi/xrpod.service`.

## Install on a phone or tablet

Connect to the same Wi-Fi as the Pi, open `http://xrpod.local` (or the Pi's
IP address), then:

- **iPhone / iPad (Safari):** tap **Share** → **Add to Home Screen**.
- **Android (Chrome):** tap **⋮** → **Add to Home screen**.

It opens full-screen with the XRPod icon, like an app.

## API (for Unity or scripts)

Setting up the Unity side: see [`unity/README.md`](unity/README.md).

| Method | Path | What it does |
|---|---|---|
| `GET` | `/api/settings` | Current settings |
| `PATCH` | `/api/settings` | Change settings, e.g. `{"fan_speed_pct": 40}`. Returns the saved settings, or `400` with an `error` message |
| `GET` | `/api/readings/latest` | Newest sensor reading |
| `GET` | `/api/history?limit=50` | Newest changes first |
| `GET` | `/api/events` | Live stream (Server-Sent Events): `settings`, `reading`, `history` |

```bash
curl http://xrpod.local/api/settings
curl -X PATCH http://xrpod.local/api/settings \
  -H "Content-Type: application/json" -d '{"selected_scent": "pine"}'
```

## Security

The HUD is meant for the pod's local network. **Anyone on the same Wi-Fi can
open it and change settings**; there's no login. Use a private network for
the pod, such as your own router or a hotspot from a phone or the Pi, not
open campus Wi-Fi.

What's in place:

- The Pi rejects invalid values before they reach the hardware.
- Other websites can't change settings through a visitor's browser (CSRF
  protection): writes must be JSON, and the browser's `Origin` must match
  the Pi.
- Only files inside `hud/dist/` are served, so the database and code aren't
  reachable.

**Remote access** (controlling the pod from off its network) isn't set up.
The safest way to add it later is [Tailscale](https://tailscale.com) on the
Pi and the phones, rather than opening a port on the router.
