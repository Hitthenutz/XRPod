# XRPod VR (Unity)

The Unity project lives in its own repo, not here. Unity projects are large
and full of binary assets (models, textures, audio, scenes). They need Git
LFS and a Unity-specific `.gitignore`, and keeping them here would make every
clone of the HUD and Pi code slow.

**Suggested repo:** `Hitthenutz/XRPod-VR`. Create it from GitHub's **Unity**
`.gitignore` template, then run `git lfs install` and track the big asset
types (`*.fbx`, `*.png`, `*.psd`, `*.wav`, `*.unity`, …) before the first
commit.

## How Unity can talk to the pod

The Pi serves a small JSON API on the pod's network (full list in the main
README's **API** section). Unity can use it with `UnityWebRequest`; the
headset must be on the same Wi-Fi as the Pi.

- **Read what the pod is doing:** `GET http://xrpod.local/api/settings` and
  `GET http://xrpod.local/api/readings/latest`. Polling every second or two
  is fine; there's no usage limit.
- **Drive the pod from a scene** (e.g. a forest scene turns on pine scent):
  `PATCH http://xrpod.local/api/settings` with
  `Content-Type: application/json` and a body like
  `{"selected_scent": "pine", "scent_intensity_pct": 60}`. The Pi validates
  it and still enforces every hardware safety rule. The change also shows up
  in the HUD and its History panel.
- **Live updates without polling:** `GET /api/events` is a Server-Sent Events
  stream (`settings`, `reading` and `history` events). Unity has no built-in
  SSE client, so polling is simpler unless you need instant updates.
