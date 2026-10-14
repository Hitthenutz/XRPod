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

| Option | How | Trade-off |
|---|---|---|
| **Pi on the local network** (recommended) | The Pi agent runs a small WebSocket or UDP server; Unity connects to the Pi's IP. | Fast and doesn't count against the Base44 quota. Headset and Pi must be on the same Wi-Fi. |
| **Through Base44** | Unity reads `PodSettings` / `SensorReading` over HTTPS with `UnityWebRequest`, the same way `pi-agent/agent.py` does. | Works from anywhere, but polling uses Base44 requests. Keep it to every 15 s or more. |

The data Unity needs is already defined in this repo:

- `base44/entities/PodSettings.jsonc`: what the pod should be doing
  (scent, fan, heater/AC, targets)
- `base44/entities/SensorReading.jsonc`: what it's actually doing

If the VR experience needs to *drive* the pod (e.g. a scene triggers pine
scent), send that through the Pi rather than writing to PodSettings directly,
so the Pi stays the one place that enforces hardware safety.
