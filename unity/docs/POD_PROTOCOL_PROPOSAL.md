# Proposal: how the Pi and the VR app talk

**Status: draft, not agreed.** To be confirmed with the central-system
(Pi) teammate. Nothing here exists on the Pi yet, and nothing on the Pi
has been changed. Unity's `HttpPodLink.cs` is a draft written against this
proposal. If the team picks something else, only that one file changes;
zone detection and environment switching don't.

**Pi/HUD teammate:** start with the
[checklist at the end](#checklist-for-the-pihud-teammate). It lists every
step, the exact rules, and commands to test without a headset.

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

## Checklist for the Pi/HUD teammate

Everything you'd need to build your side, in order. Nothing here is
built yet, and it's a proposal: change anything that doesn't fit, just
tell the VR side so both match.

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

### Step 1: the setting (`pi-agent/store.py`)

Same pattern as `selected_scent`:

- `ENVIRONMENTS = ("none", "beach", "forest", "desert", "sponsor")`
- `SETTINGS_SCHEMA["selected_environment"]`, checked against `ENVIRONMENTS`
- `DEFAULT_SETTINGS["selected_environment"] = "none"`

Because it's a normal setting, `PATCH /api/settings` already saves it,
logs it in history and pushes it to the HUD. Nothing else is needed.

### Step 2: the HUD picker (`src/`)

- Add `selected_environment: "none"` to `DEFAULT_SETTINGS` in
  `src/lib/podSettings.js` (and the list of worlds, like `SCENTS`).
- Add a picker (Beach / Forest / Desert / Sponsor / None). Save through
  `applyChanges()` in `usePodSettings.js` like every other control.
- Nice to have: show the latest VR state, e.g. "VR: Forest, windy zone"
  (see step 3), or "VR: not connected" if nothing arrived for ~15 s.

### Step 3: the endpoint (`pi-agent/web.py`)

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
| `environment` | `beach`, `forest`, `desert`, `sponsor` |
| `zone_id` | `null`, or text 1 to 64 characters |
| `zone_type` | `neutral`, `hot`, `cool`, `windy` |
| `zone_tracking` | `true` or `false` |
| `reason` | `environment_changed`, `zone_entered`, `zone_exited` |

Two extra checks: if `zone_id` is `null`, `zone_type` must be `neutral`;
if `zone_tracking` is `false`, `zone_id` must be `null`.

### Step 4: tests (`pi-agent/test_pod.py`)

At least: a good message is accepted, each bad field gets `400`, an unknown
field gets `400`, an old `seq` doesn't replace a newer one, a new
`session_id` does, a cross-origin request gets `403`, and
`selected_environment` rejects unknown worlds.

### Testing without the headset

These pretend to be the headset. Run them on the Pi (`localhost`); from
another computer use the Pi's address. The Pi service uses port 80, so
drop `:8080` there; `python3 pi-agent/agent.py` on a laptop uses 8080.

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
(`dotnet run --project unity/OfflineTests -- demo`).

### What the VR side needs back

- "Yes" or changes to this proposal (field names, rules, replies).
- The answers to the open questions above, especially the Pi's address
  on the pod's Wi-Fi.
- A heads-up when it's on a branch, so we can test the headset against it.
