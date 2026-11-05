# XRPod VR (Unity)

The VR app for Meta Quest 3. It shows the experience the operator picks in
the HUD (beach, forest, desert or the sponsor's) and tells the Pi which
experience and zone (hot, cool, windy, neutral) the user is in. It only
reports: it never drives the fan, heater, AC or scent. The Pi decides what
to do with the reports.

This folder is the Unity project (Unity 6.6, URP, OpenXR).

| Path | What's in it |
|---|---|
| `Assets/XRPod/Scripts/Core/` | The logic (zones, environments, messages), plain C# with no Unity dependency |
| `Assets/XRPod/Scripts/Unity/` | The Unity components that connect the logic to scenes |
| `OfflineTests/` | Tests for the logic that run without Unity |
| `docs/` | How it fits together, setup, sponsor content, the Pi protocol |
| `.gitignore` | Keeps Unity's generated folders (`Library/`, `Temp/`, builds) out of git |

## Start here

- [docs/VR_ARCHITECTURE.md](docs/VR_ARCHITECTURE.md): how the code fits together
- [docs/UNITY_SETUP.md](docs/UNITY_SETUP.md): setting up the project and building for the Quest 3
- [docs/SPONSOR_INTEGRATION.md](docs/SPONSOR_INTEGRATION.md): adding the sponsor's experience
- [docs/POD_PROTOCOL_PROPOSAL.md](docs/POD_PROTOCOL_PROPOSAL.md): how the headset and the Pi talk

Run the tests (needs the .NET 8 SDK) from the repo root:

```bash
dotnet run --project vr/OfflineTests
```

## Large files

Models, textures and audio are binary and can be big. Agree on Git LFS
with the team before committing them, and don't commit the sponsor's
content without their permission.
