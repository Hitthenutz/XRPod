# How the Pi and the VR app talk

**Status: agreed and built (November 2026).** The Pi side (`pi/vr.py`,
`pi/web.py`, `pi/store.py`) and the HUD (Manual/Auto switch, environment
picker, VR status line) are on `main`. Unity's `HttpPodLink.cs` uses it.
This file is the reference for the message format. If the transport ever
changes, only `HttpPodLink.cs` changes on the Unity side; zone detection
and environment switching don't.

The [checklist at the end](#checklist-for-the-pihud-teammate) is what the
Pi side was built from, with commands to test it without a headset.

## What's needed

1. The HUD picks one of four experiences (beach, forest, desert, sponsor),
   and Unity shows it.
2. Unity tells the Pi which experience and zone the user is in.
3. The Pi decides what to do with that. In **manual** mode it doesn't change
   the hardware; in **automatic** mode it runs its own control logic.
   Unity sends the same messages in both modes and never sends
   fan/heater/AC/scent values.

## Network and transport

- **Wi-Fi, no internet:** the pod runs on its own local Wi-Fi. The headset,
  the Pi, the HUD and the ESP32 nodes only talk to each other, so no
  internet is needed. Phones and the Quest may warn "connected, no
  internet": choose to stay connected, and forget other saved networks on
  the pod's headset so it doesn't switch away.
- **The Pi's address:** for now the Pi joins Zainab's hotspot, where it's
  at `10.199.194.129`. A hotspot hands out addresses, so this can change
  when the Pi reconnects (check with `hostname -I` on the Pi). The plan is
  for the Pi to run its own hotspot; then it is the router and its address
  never changes (often `10.42.0.1` with NetworkManager). Use the address in
  Unity: `xrpod.local` may not resolve on the Quest.
- **TCP:** HTTP runs over TCP, so this proposal is TCP over Wi-Fi, as in
  the original plan, using the web server the Pi already runs
  (`pi/web.py`). A custom TCP socket protocol would also work, and
  Unity is built so it could switch (see the end).
- **MQTT** (Pi ↔ ESP32 hardware) is separate and unaffected.

## 1. Selection: a new setting

Add `selected_environment` to the settings, like every other HUD control.
It then gets validation, history and live updates for free:

- `pi/store.py`:
  `ENVIRONMENTS = ("none", "beach", "forest", "desert", "sponsor")`,
  `SETTINGS_SCHEMA["selected_environment"]` (validated like `selected_scent`),
  `DEFAULT_SETTINGS["selected_environment"] = "none"`
- `hud/src/lib/podSettings.js`: the same default, plus a picker in the HUD

Unity polls `GET /api/settings` about once a second and follows
`selected_environment` (every poll, so it stays in step with the HUD).
`"none"` shows the headset's **waiting room**; `"sponsor"` shows a
"coming soon" room until the sponsor's content is in the app. Unknown
values are ignored and logged once.

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
| `environment` | `beach`, `forest`, `desert`, `sponsor`, or `none` (the waiting room: `zone_id` null, `zone_tracking` false) |
| `zone_id` | Zone's id, e.g. `beach-waterline`, or `null` when no zone is known. **This is what the Pi uses:** it looks up the zone's recipe (see `ZONES.md`) |
| `zone_type` | `neutral`, `hot`, `cool`, `windy`: only a rough hint |
| `zone_tracking` | `false` when zones aren't detected in this environment (the sponsor's, for now). `zone_type` is then always `neutral`, meaning "unknown" |
| `reason` | `environment_changed`, `zone_entered`, `zone_exited` |

Each message is the full current state, so the Pi only has to keep the
latest. Unity sends one when something changes, and resends the latest
every ~5 s so the Pi catches up after a restart.

Suggested Pi behaviour:

- Keep `web.py`'s protections: JSON only, `MAX_BODY_BYTES`, the `Origin`
  check (Unity sends no `Origin`, so it passes like `curl`).
- Validate every field; reject unknown fields and values with `400`.
- Ignore a message whose `seq` is lower than the last one from the same
  `session_id` (reply `200` anyway). A message with the **same** `seq` is
  the ~5 s repeat: keep the state, but count it as "heard from the headset
  just now", or the HUD shows "not connected" while the user stands still.
- Keep it in memory, not a database row per step. Expose it with
  `GET /api/vr/state`, and publish a `vr` Server-Sent Event so the HUD can
  show "VR: forest / forest-clearing".
- In automatic mode, the control loop looks up the recipe for the current
  `zone_id` (target temperature, fan, humidity, scent; see `ZONES.md`) and
  applies it. `hardware.py`'s safety rules still apply.

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

## Decided

- HTTP polling to start with (above).
- After 15 s without hearing from the headset the Pi reports
  `connected: false` and the HUD shows "VR: not connected". The headset's
  ~5 s repeat counts as hearing from it.
- Unity only reports. It never `PATCH`es settings (an older `vr/README.md`
  suggested it; doing both would let Unity drive the hardware).
- Auto mode looks up a recipe per `zone_id` (`ZONES.md`).

## Open questions

- Does the Pi run its own hotspot (fixed address), or keep joining
  Zainab's hotspot (address can change)?
- What should automatic mode do when `zone_tracking` is `false` (sponsor)
  or `zone_id` is `null`?

## Checklist for the Pi/HUD teammate

What the Pi side was built from, in order (done). Kept as a reference and
for the test commands; if anything changes, update both sides.

### The short version

> The headset needs two things from the Pi:
>
> 1. **Which world to show.** Add a `selected_environment` setting
>    (`none`, `beach`, `forest`, `desert`, `sponsor`) and a picker for it
>    in the HUD. The headset reads `GET /api/settings` about once a second
>    and switches when the value changes.
> 2. **A place to send where the user is.** Add `PUT /api/vr/state`. The
>    headset sends a small JSON message every time the world or zone
>    changes, and repeats the latest one every ~5 s. Keep the newest one
>    in memory and show it in the HUD.
>
> The headset never sends fan/heater/AC/scent values. What to do with a
> zone (in automatic mode) is up to the Pi.

### Step 1: the setting (`pi/store.py`)

Same pattern as `selected_scent`:

- `ENVIRONMENTS = ("none", "beach", "forest", "desert", "sponsor")`
- `SETTINGS_SCHEMA["selected_environment"]`, checked against `ENVIRONMENTS`
- `DEFAULT_SETTINGS["selected_environment"] = "none"`

Because it's a normal setting, `PATCH /api/settings` already saves it,
logs it in history and pushes it to the HUD. Nothing else is needed.

### Step 2: the HUD picker (`hud/src/`)

- Add `selected_environment: "none"` to `DEFAULT_SETTINGS` in
  `hud/src/lib/podSettings.js` (and the list of worlds, like `SCENTS`).
- Add a picker (Beach / Forest / Desert / Sponsor / None). Save through
  `applyChanges()` in `usePodSettings.js` like every other control.
- Nice to have: show the latest VR state, e.g. "VR: Forest, windy zone"
  (see step 3), or "VR: not connected" if nothing arrived for ~15 s.

### Step 3: the endpoint (`pi/web.py`)

`PUT /api/vr/state` (today `do_PUT` answers every path with `405`):

- Keep the same checks as `PATCH /api/settings`: same-origin check, JSON
  content type, body size up to `MAX_BODY_BYTES`.
- Check every field with the rules below. Any problem: `400` with
  `{"error": "..."}`, like the existing endpoints.
- If `seq` isn't higher than the last one stored for the same
  `session_id`, keep the stored one (an old message arrived late) but
  still reply `200`. A new `session_id` means the app restarted: accept
  it whatever its `seq`.
- Keep only the latest message, in memory. No database rows (it can
  arrive several times a second while walking around).
- Reply `200` with the stored state as JSON.
- Publish it to the HUD as a `vr` Server-Sent Event.
- Add `GET /api/vr/state`: the stored state, or `null` before the
  headset has sent anything.

**Rules.** All 7 fields are required, and any other field is rejected.

| Field | Allowed |
|---|---|
| `session_id` | text, 1 to 64 characters (the headset sends 12 letters/digits) |
| `seq` | whole number, 1 or more (not `true`/`false`) |
| `environment` | `none`, `beach`, `forest`, `desert`, `sponsor` |
| `zone_id` | `null`, or text 1 to 64 characters |
| `zone_type` | `neutral`, `hot`, `cool`, `windy` |
| `zone_tracking` | `true` or `false` |
| `reason` | `environment_changed`, `zone_entered`, `zone_exited` |

Two extra checks: if `zone_id` is `null`, `zone_type` must be `neutral`;
if `zone_tracking` is `false`, `zone_id` must be `null`.

### Step 4: tests (`pi/test_pod.py`)

At least: a good message is accepted, each bad field gets `400`, an unknown
field gets `400`, an old `seq` doesn't replace a newer one, a new
`session_id` does, a cross-origin request gets `403`, and
`selected_environment` rejects unknown worlds.

### Testing without the headset

These pretend to be the headset. Run them on the Pi (`localhost`); from
another computer use the Pi's address. The Pi service uses port 80, so
drop `:8080` there; `python3 pi/agent.py` on a laptop uses 8080.

Pick a world, as the HUD would:

```bash
curl -i -X PATCH http://localhost:8080/api/settings -H "Content-Type: application/json" -d '{"selected_environment":"forest"}'
```

Send a zone, as the headset would. Expect `200`:

```bash
curl -i -X PUT http://localhost:8080/api/vr/state -H "Content-Type: application/json" -d '{"session_id":"test1","seq":2,"environment":"forest","zone_id":"clearing-wind","zone_type":"windy","zone_tracking":true,"reason":"zone_entered"}'
```

A bad zone type. Expect `400`:

```bash
curl -i -X PUT http://localhost:8080/api/vr/state -H "Content-Type: application/json" -d '{"session_id":"test1","seq":3,"environment":"forest","zone_id":"clearing-wind","zone_type":"lava","zone_tracking":true,"reason":"zone_entered"}'
```

An older message arriving late. Expect `200`, and the stored state still
has `seq` 2:

```bash
curl -i -X PUT http://localhost:8080/api/vr/state -H "Content-Type: application/json" -d '{"session_id":"test1","seq":1,"environment":"forest","zone_id":null,"zone_type":"neutral","zone_tracking":true,"reason":"environment_changed"}'
```

Read what the Pi stored:

```bash
curl -i http://localhost:8080/api/vr/state
```

These example messages are copied from what the VR code really produces
(`dotnet run --project vr/OfflineTests -- demo`).

### What the VR side needs back

- "Yes" or changes to this proposal (field names, rules, replies).
- The answers to the open questions above, especially the Pi's address
  on the pod's Wi-Fi.
- A heads-up when it's on a branch, so we can test the headset against it.
