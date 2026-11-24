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
| `beach-umbrella-shade` | Under any umbrella (one id for all of them) | Shade, a little cooler | 77 | 20 | 45 | none |

In `Beach_v1`, **XRPod → Finish Beach v1** (and **15% Bigger**) puts a
`beach-umbrella-shade` zone under every umbrella. Shade beats the sunny
shore (priority 15 vs 10); the waterline's wind and spray beat shade (20).

### Forest

`Forest_v1` is made from the free Fantasy Forest pack (ForestVision was
too slow on the headset) with **XRPod → Make Forest v1 (from Fantasy
Forest) + Place Zones**. The zones come from the trees' real shade, the
same way as the desert's (below): for the check, each nearby tree's leaf
and trunk meshes block the sun. Run **XRPod → Forest: Place Zones From
Real Shade** again after moving the sun; a map is saved to
`vr/Logs/xrpod-forest-zones.png`.

| Zone id | Where | What you'd feel | Temp °F | Fan % | Humidity % | Scent |
|---|---|---|---|---|---|---|
| `forest-open` | Between the trees in the sun (base) | Mild, light breeze, earthy | 72 | 15 | 55 | pine 25 % |
| `forest-shade` | In a tree's shadow | Cool, still, damp | 66 | 5 | 65 | pine 35 % |
| `forest-clearing` | Open sky at least 7 m from any tree | Warmer, breezier | 78 | 30 | 45 | pine 15 % |
| `forest-hilltop` | The highest open ground (top tenth, at least 2 m above the start) | Windy | 70 | 60 | 50 | pine 20 % |

Priorities: shade 15, clearing and hilltop 10, open 0. The photo forest
(`Forest`, with rain) is still in the project as the test world.

### Desert

Placed from the real shadows in `Desert_v1` with **XRPod → Desert: Place
Zones From Real Shade**: every square metre within 60 m of the start is
checked for whether you can walk there and whether a line from your body
to the sun is blocked. Shade zones follow each shadow's shape (several
boxes with one id). Run it again after moving the sun or the scenery; a
map is saved to `vr/Logs/xrpod-desert-zones.png`.

| Zone id | Where | What you'd feel | Temp °F | Fan % | Humidity % | Scent |
|---|---|---|---|---|---|---|
| `desert-open` | Open sun (base) | Hot and dry | 92 | 15 | 15 | none |
| `desert-ridge` | The highest open ground (top tenth, at least 2 m above the start) | Hot, strong dry wind | 90 | 70 | 10 | none |
| `desert-shade` | In the shadow of rocks, walls, the raft or the tower | Shade: a bit cooler | 82 | 10 | 15 | none |
| `desert-covered` | Under a roof or awning (shade with something overhead) | Cooler, still air | 78 | 5 | 20 | none |
| `desert-campfire` | Within about 1.7 m of a fire pit | Warm on the skin | 95 | 0 | 15 | none |

Priorities: campfire 25, covered 20, shade 15, ridge 10, open 0.

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
