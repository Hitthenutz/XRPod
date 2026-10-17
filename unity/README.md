# XRPod VR (Unity)

The Unity project lives in this folder: `unity/` is the project root, so
`Assets/`, `Packages/` and `ProjectSettings/` sit directly inside it.

## One-time setup

1. **Install Git LFS** (`git lfs install`, once per computer). Models,
   textures, audio and other binaries under `unity/` are stored with LFS
   (rules in the repo's `.gitattributes`), which keeps clones of the repo
   small. The **Repo size** check in CI fails if a large binary slips in
   without LFS.
2. **Create the project.** Unity Hub won't create a project in a folder that
   already has files, so create it somewhere else first (e.g. `~/XRPodVR`),
   then move its `Assets/`, `Packages/` and `ProjectSettings/` folders into
   `unity/` and open `unity/` with **Add project from disk**. Delete the
   temporary project.
3. **Editor settings** (Edit → Project Settings → Editor):
   - Version Control → Mode: **Visible Meta Files**
   - Asset Serialization → Mode: **Force Text**, so scenes and prefabs
     diff and merge as text.
4. Write down the Unity version (`ProjectSettings/ProjectVersion.txt` is
   committed) so everyone opens the project with the same editor.

`unity/.gitignore` keeps `Library/`, `Temp/`, `Logs/`, builds and IDE files
out of git. Always commit an asset together with its `.meta` file.

## Suggested layout

Keep your own work under one folder so it's separate from imported packages:

```
unity/Assets/XRPod/
├── Scenes/              # one scene per environment (forest, beach, …)
├── Scripts/
│   ├── PodLink/         # talks to the Pi's API (see below)
│   └── Environments/    # what each scene asks the pod to do
├── Prefabs/
├── Materials/
├── Models/
└── Audio/
```

## How Unity talks to the pod

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
  in the HUD and its History panel. Don't send an `Origin` header; the Pi
  rejects writes whose `Origin` doesn't match its own address.
- **Live updates without polling:** `GET /api/events` is a Server-Sent Events
  stream (`settings`, `reading` and `history` events). Unity has no built-in
  SSE client, so polling is simpler unless you need instant updates.

Field names and allowed values are defined in `pi/store.py`
(`SETTINGS_SCHEMA`, `SCENTS`). Keep the Unity side in step when they change.
