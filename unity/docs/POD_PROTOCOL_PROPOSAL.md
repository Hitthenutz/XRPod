# Proposal: how the Pi and the VR app talk

**Status: draft, not agreed.** To be confirmed with the central-system
(Pi) teammate. Nothing here exists on the Pi yet, and nothing on the Pi
has been changed. Unity's `HttpPodLink.cs` is a draft written against this
proposal. If the team picks something else, only that one file changes;
zone detection and environment switching don't.

## What's needed

1. The HUD picks one of four experiences (beach, forest, desert, sponsor),
   and Unity shows it.
2. Unity tells the Pi which experience and zone the user is in.
3. The Pi decides what to do with that. In **manual** mode it doesn't change
   the hardware; in **automatic** mode it runs its own control logic.
   Unity sends the same messages in both modes and never sends
   fan/heater/AC/scent values.

## Network and transport

- **Wi-Fi:** Quest 3 and Pi on the same network. To be confirmed: the Pi
  may run the hotspot itself, in which case it has a fixed address (often
  `10.42.0.1` with NetworkManager's hotspot) that Unity can use directly.
  `xrpod.local` may not resolve on the Quest.
- **TCP:** HTTP runs over TCP, so this proposal is TCP over Wi-Fi, as in
  the original plan, using the web server the Pi already runs
  (`pi-agent/web.py`). A custom TCP socket protocol would also work, and
  Unity is built so it could switch (see the end).
- **MQTT** (Pi ↔ ESP32 hardware) is separate and unaffected.

## 1. Selection: a new setting

Add `selected_environment` to the settings, like every other HUD control.
It then gets validation, history and live updates for free:

- `pi-agent/store.py`:
  `ENVIRONMENTS = ("none", "beach", "forest", "desert", "sponsor")`,
  `SETTINGS_SCHEMA["selected_environment"]` (validated like `selected_scent`),
  `DEFAULT_SETTINGS["selected_environment"] = "none"`
- `src/lib/podSettings.js`: the same default, plus a picker in the HUD

Unity polls `GET /api/settings` (already exists) about once a second and
switches when `selected_environment` **changes**. It ignores `"none"` and
unknown values, and ignores `"sponsor"` until the sponsor content is in the
app (it logs a warning).

The manual/automatic switch (e.g. a `control_mode` setting) belongs to the
Pi. Unity doesn't need it.

## 2. VR state: a new endpoint

```
PUT /api/vr/state
Content-Type: application/json

{"session_id":"3f9c1a2b7d4e","seq":7,"environment":"forest",
 "zone_id":"clearing-wind","zone_type":"windy","zone_tracking":true,
 "reason":"zone_entered"}
```

| Field | Values |
|---|---|
| `session_id` | Random string, new each time the app starts |
| `seq` | Counts up from 1 within a session |
| `environment` | `beach`, `forest`, `desert`, `sponsor` |
| `zone_id` | Zone's id, or `null` when neutral |
| `zone_type` | `neutral`, `hot`, `cool`, `windy` |
| `zone_tracking` | `false` when zones aren't detected in this environment (the sponsor's, for now). `zone_type` is then always `neutral`, meaning "unknown" |
| `reason` | `environment_changed`, `zone_entered`, `zone_exited` |

Each message is the full current state, so the Pi only has to keep the
latest. Unity sends one when something changes, and resends the latest
every ~5 s so the Pi catches up after a restart.

Suggested Pi behaviour:

- Keep `web.py`'s protections: JSON only, `MAX_BODY_BYTES`, the `Origin`
  check (Unity sends no `Origin`, so it passes like `curl`).
- Validate every field; reject unknown fields and values with `400`.
- Ignore a message whose `seq` isn't higher than the last one from the
  same `session_id` (reply `200` anyway).
- Keep it in memory, not a database row per step. Expose it with
  `GET /api/vr/state`, and publish a `vr` Server-Sent Event so the HUD can
  show "VR: forest / windy zone".
- In automatic mode, the control loop reads the latest state and applies
  its own rules. `hardware.py`'s safety rules still apply.

## Why HTTP polling to start with

- The Pi already runs an HTTP server with validation, CSRF protection and
  tests. Two small additions cover everything, with no new server, port or
  dependency.
- Each message is the full state, so a dropped request or a Pi/headset
  restart heals itself on the next message, with no connection state to
  manage.
- It's easy to test by hand (`curl`, a browser).
- Cost: up to ~1 s delay for a HUD selection to reach the headset, which
  is fine for switching environments. Zone changes go out from Unity
  immediately.

A persistent TCP socket (or WebSocket) would cut that delay, but it needs
a new server on the Pi, reconnection logic on both sides and its own
message framing. Worth it later if the delay matters.

## Switching protocols later

Unity talks to the Pi only through `IPodLink` (receive "show environment X",
send "here's the state"). A raw TCP version would be a new `TcpPodLink.cs`
sending the same JSON, one message per line, over a socket, with nothing
else changing in Unity. The message fields above would stay the same.

## Open questions

- HTTP polling now, or a persistent connection from the start?
- Does the Pi run the Wi-Fi hotspot? What address should Unity use?
- Should the Pi treat VR state older than N seconds as "VR disconnected"?
- What should automatic mode do when `zone_tracking` is `false` (sponsor)?
- `vr/README.md` on `main` suggests Unity `PATCH`es settings directly.
  Should that be replaced by this? Doing both would let Unity drive the
  hardware, which goes against the report-only design.
