# XRPod VR: how the code fits together

Unity's job is to **show** an environment and **report** where the user is
in it. It never drives the fan, heater, AC or scent. The Pi gets the reports
and decides what to do: nothing in manual mode, adjust the pod in
automatic mode. Zone detection works the same in both modes.

```
                     ┌──────────────────────── Unity (Quest 3) ───────────────────────┐
                     │                                                                │
 HUD ──▶ Pi ──selected environment──▶ IPodLink ──▶ EnvironmentController ──▶ EnvironmentSceneLoader
                     │   (HttpPodLink,            │  (checks request,          (loads the scene)
                     │    or InMemoryPodLink      │   resets zones)                              │
                     │    offline)                ▼                                            │
 Pi ◀──VR state───── IPodLink ◀── VrSession ◀── ZoneStateTracker ◀── ZoneVolume ◀── PlayerZoneProbe
                     │            (one message   (active zone,       (trigger      (collider on
                     │             per change)    overlaps, dupes)    collider)     the head)
                     └────────────────────────────────────────────────────────────────┘
```

## Two layers

| Folder | Uses Unity? | Tested how |
|---|---|---|
| `Assets/XRPod/Scripts/Core/` | No. The `XRPod.VR.Core` assembly has *No Engine References* set, so Unity refuses to compile it if `UnityEngine` creeps in | `unity/OfflineTests` on any PC with the .NET 8 SDK |
| `Assets/XRPod/Scripts/Unity/` | Yes (MonoBehaviours) | In the Unity Editor and on the headset |

All the decisions live in Core. The Unity scripts only translate Unity
callbacks (triggers, scene loading, HTTP) into calls on Core.

## Core

| File | What it does |
|---|---|
| `EnvironmentId.cs` | `Beach`, `Forest`, `Desert`, `Sponsor` (+ `None`), and their names on the wire (`"beach"`, …) |
| `ZoneType.cs` | `Neutral`, `Hot`, `Cool`, `Windy` |
| `ZoneDefinition.cs` | One zone: id, type, environment, priority |
| `ZoneStateTracker.cs` | Which zones the player is inside, and which one is **active** |
| `EnvironmentController.cs` | Accepts or rejects environment requests; resets zones on a switch; per-environment *available* and *zone tracking* switches |
| `VrEvents.cs` | `ZoneChangedEvent`, `EnvironmentChangedEvent` and result codes |
| `IPodLink.cs` | The communication interface: receive environment requests, publish state |
| `PodStateMessage.cs` | What Unity reports, and its JSON |
| `InMemoryPodLink.cs` | Fake link for tests and offline Editor runs |
| `VrSession.cs` | Connects all of the above for one run of the app |

## Unity

| File | Goes on | What it does |
|---|---|---|
| `VrSystemRoot.cs` | An object in the Bootstrap scene | Creates the `VrSession`; picks the start environment |
| `PlayerZoneProbe.cs` | A child of the XR Origin's Main Camera | Marks the one collider that counts as "the player" |
| `ZoneVolume.cs` | Each zone's trigger collider in an environment scene | Reports enter/exit to the tracker |
| `EnvironmentSceneLoader.cs` | The Bootstrap scene | Loads/unloads environment scenes additively |
| `EditorTestControls.cs` | The Bootstrap scene | Keys 1/2/3 switch environment; on-screen status |
| `HttpPodLink.cs` | The Bootstrap scene (optional) | **Draft** HTTP link to the Pi, see `POD_PROTOCOL_PROPOSAL.md` |

## Zone rules

- **Active zone:** the highest `priority` among zones the player is
  inside; on a tie, the one entered last. None: **neutral**.
- **No duplicates:** an event fires only when the active zone actually
  changes. Re-entering a zone you're in, leaving one you're not in, or
  overlap changes that leave the same zone on top fire nothing.
- **Overlaps:** leaving the active zone falls back to the next zone you're
  still inside, not straight to neutral. Use `priority` for a zone nested
  inside another (e.g. a cool cave, priority 10, inside a hot desert
  area, priority 0).
- **Environment switch:** every zone is cleared (back to neutral) and the
  tracker accepts only zones belonging to the new environment, so late
  triggers from the unloading scene are ignored.
- **Zone ids** must be unique within an environment.

## Four experiences

Beach, Forest and Desert are always available, with zone tracking on. The
sponsor's experience (`Sponsor`) starts **unavailable** (requests for it
are ignored and logged) with **zone tracking off** (zones ignored, player
stays neutral, Pi told `zone_tracking: false`). Both are switched on in
`VrSystemRoot` once their files are integrated; see
`SPONSOR_INTEGRATION.md`.

## What the Pi receives

One message per change, always the full current state:

```json
{"session_id":"3f9c1a2b7d4e","seq":7,"environment":"forest",
 "zone_id":"clearing-wind","zone_type":"windy","zone_tracking":true,
 "reason":"zone_entered"}
```

`reason` is `environment_changed`, `zone_entered` or `zone_exited`.
Switching environment sends one `environment_changed` message with
`zone_type: "neutral"`; the zone reset doesn't send one of its own.

Unity sends the same messages in manual and automatic mode. It doesn't
know which mode the pod is in; the Pi decides whether to act.

The transport (HTTP today, as a draft) lives only in the `IPodLink`
implementation; see `POD_PROTOCOL_PROPOSAL.md`.
