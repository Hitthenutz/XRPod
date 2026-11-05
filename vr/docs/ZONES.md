# Zones: where they are and how they should feel

**Status: first draft.** The places are in the placeholder scenes now
(menu **XRPod → Create Test Scenes**). The values are suggestions for the
Pi team to start from and tune.

## How zones drive the pod

1. The headset reports **which zone you're in**, by its id, e.g.
   `beach-waterline` (the `zone_id` field in `PUT /api/vr/state`).
2. The Pi keeps a **recipe** for each zone id: target temperature, fan
   speed, humidity and scent.
3. In **auto mode** the Pi applies the recipe, using its sensors to get
   there (e.g. heater on until the room reaches the target). In **manual
   mode** it does nothing with it. All of `hardware.py`'s safety rules
   still apply.

So the VR side decides *where* each zone is and what it's meant to feel
like; the Pi side decides the *numbers*. Recipes can be tuned on the Pi
without rebuilding the headset app.

- **Base zone:** each world has one zone covering all of it
  (`beach-open`, `forest-open`, `desert-open`). It's what the world feels
  like anywhere outside the other zones, so the user is always in a zone.
- **Rings:** to make something stronger as you get closer, zones sit
  inside each other with a higher priority. Walking towards the sea goes
  `beach-open` → `beach-shore` → `beach-waterline`.
- **`zone_type`** (hot, cool, windy, neutral) is only a rough hint. Use
  `zone_id` for recipes.
- **`zone_id: null`** means no zone is known: right after switching worlds,
  or `zone_tracking: false` (the sponsor's world for now). Suggested: use
  the HUD's manual settings, or a gentle default.

## Zones

Suggested starting values. The pod's ranges: temperature 50–95 °F,
humidity 0–100 %, fan 0–100 %, scents `none`, `lavender`, `pine`,
`citrus`, `ocean`, `rain`.

### Beach

The sea is ahead of the start point (+z).

| Zone id | Where | What you'd feel | Temp °F | Fan % | Humidity % | Scent |
|---|---|---|---|---|---|---|
| `beach-open` | Everywhere else (base) | Warm sun, light breeze | 84 | 15 | 40 | none |
| `beach-shore` | Band of sand before the water | Breezier, a hint of sea air | 78 | 45 | 55 | ocean 30 % |
| `beach-waterline` | At the waves (inside the shore band) | Cool, very windy, damp, salty | 72 | 75 | 70 | ocean 70 % |
| `beach-dunes` | Dunes to the right | Breezy and dry | 82 | 50 | 30 | none |
| `beach-palm-shade` | Under the palm behind the start | Shade, a little cooler | 76 | 20 | 45 | none |

### Forest

| Zone id | Where | What you'd feel | Temp °F | Fan % | Humidity % | Scent |
|---|---|---|---|---|---|---|
| `forest-open` | Under the trees (base) | Mild, still, earthy | 70 | 10 | 60 | pine 30 % |
| `forest-clearing` | Sunny clearing ahead | Warmer, light breeze | 78 | 25 | 50 | pine 15 % |
| `forest-rain` | Rainy area, front left (light cloud) | Cooler, damp | 66 | 20 | 75 | rain 40 % |
| `forest-rain-heavy` | Middle of the rain (dark cloud) | Cool, very wet, gusty | 62 | 30 | 90 | rain 80 % |
| `forest-stream` | Along the stream, right | Cool and humid | 66 | 15 | 70 | pine 20 % |

### Desert

| Zone id | Where | What you'd feel | Temp °F | Fan % | Humidity % | Scent |
|---|---|---|---|---|---|---|
| `desert-open` | Open sun (base) | Hot and dry | 92 | 15 | 15 | none |
| `desert-ridge` | Ridge to the left | Hot, strong dry wind | 90 | 70 | 10 | none |
| `desert-rock-shade` | Shade next to the big rock, far right | Shade: a bit cooler | 82 | 10 | 15 | none |
| `desert-cave-mouth` | Cave entrance ahead | Shaded, cooler | 80 | 5 | 20 | none |
| `desert-cave-inside` | Inside the cave | Cool, still air | 72 | 0 | 25 | none |

### Sponsor

No zones yet (`zone_tracking: false`); it shows a "coming soon" room
until the sponsor's world is in. See `SPONSOR_INTEGRATION.md`.

### Waiting room

When nothing is picked in the HUD (`selected_environment: "none"`) the
headset shows its waiting room and reports `environment: "none"` with no
zone. Suggested: the pod stays at a calm default.

## Changing zones

- Ids are `<world>-<place>`, lowercase with dashes, unique within a world,
  up to 64 characters.
- Change this list and the scenes together (the placeholder layout is in
  `Assets/XRPod/Scripts/Editor/XRPodSceneBuilder.cs`), and tell the Pi team:
  a zone without a recipe does nothing in auto mode.
- When the placeholder worlds are replaced with real art, move the zone
  objects to match the new scenery, keeping their ids.
