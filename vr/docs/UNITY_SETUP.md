# Unity setup: once the Editor is installed

Step by step, for someone new to Unity. Menu names are from Unity 6. If
something is named slightly differently in 6.6, search for it in the
Package Manager or Project Settings search box.

**Nothing here has been tried in Unity yet.** Treat the steps as a plan
and fix them as you go.

## 0. Before you start

- **Run the offline tests first** (needs the .NET 8 SDK:
  `winget install Microsoft.DotNet.SDK.8`):
  ```bash
  dotnet run --project vr/OfflineTests
  ```
  ```bash
  dotnet run --project vr/OfflineTests -- demo
  ```
- **`vr/.gitignore` keeps Unity's generated folders out of git**
  (`Library/` is gigabytes). Before committing big binary files (models,
  textures, audio), agree on Git LFS with the team.

## 1. Create the project inside `vr/`

`vr/` is the Unity project folder. Unity Hub won't create a project in a
folder that already has files, and `vr/` already holds `Assets/XRPod/`,
`OfflineTests/` and `docs/`.

1. Unity Hub → **New project** → template **Universal 3D** (URP). Name it
   `XRPodVR` and put it **outside** the repo, e.g. `C:\Users\<you>\XRPodVR`.
   Let it open once, then close Unity.
2. In File Explorer, copy from `XRPodVR` into the repo's `vr/` folder:
   - `Packages/` and `ProjectSettings/`
   - the **contents** of `XRPodVR/Assets/` into `vr/Assets/` (merge;
     keep our `Assets/XRPod/` folder)
3. Unity Hub → **Add** → **Add project from disk** → choose the repo's
   `vr/` folder. Open it with **6.6**. Delete the temporary `XRPodVR`.
4. **Edit → Project Settings → Editor**: Version Control mode **Visible Meta
   Files**, Asset Serialization **Force Text** (scenes merge as text).
5. Check the **Console** (Window → General → Console). Our scripts should
   compile with no errors. Unity creates a `.meta` file next to every
   script; commit them along with the scripts.

## Quick start: test scenes in one click

Once the project opens, menu **XRPod → Create Test Scenes** builds
placeholder versions of steps 3 to 5 for you (`XRPodSceneBuilder.cs`):

- `Assets/XRPod/Scenes/Bootstrap.unity`: the `XRPod` object (Vr System
  Root, Environment Scene Loader, Editor Test Controls) and a **desktop
  test player**: a camera at head height with the zone probe, moved with
  the keyboard and mouse (`DesktopTestMover`)
- `Beach`, `Forest`, `Desert`: coloured ground, a sky, simple shapes and
  three example zones each. A coloured pad marks each zone: red = hot,
  blue = cool, white = windy. The desert's cool cave sits inside its hot
  area to test overlapping zones.
- the Build Profile's scene list: Bootstrap, Beach, Forest, Desert

Open Bootstrap and press **Play**. **1 / 2 / 3** switch worlds, **W A S D**
walk (Shift: faster), hold the **right mouse button** to look around. Then
go through the checklist in step 6.

Running it again replaces those four scenes (it asks first). The desktop
player is only for testing on the computer; step 3 replaces it with the
XR Origin for the headset.

## 2. XR packages

**Window → Package Manager → Unity Registry**, install:

| Package | Why |
|---|---|
| **XR Plug-in Management** | Turns XR on per platform |
| **OpenXR Plugin** | The runtime Quest 3 uses |
| **XR Interaction Toolkit** | XR Origin, controller movement, Device Simulator |
| **Input System** | Controllers and our keyboard test keys (XRI installs it) |

Optional: **Unity OpenXR: Meta** adds Quest-specific features
(passthrough etc.), but we don't need it yet.

Then:

1. In Package Manager, select **XR Interaction Toolkit → Samples** and
   import **Starter Assets** and **XR Device Simulator**.
2. **Project Settings → XR Plug-in Management**:
   - **Android** tab: tick **OpenXR**, then the **Meta Quest** feature group.
   - **Windows** tab: tick **OpenXR** too (for Quest Link testing later).
3. **XR Plug-in Management → OpenXR** (Android tab): under *Enabled
   Interaction Profiles* add **Oculus Touch Controller Profile** (Quest 3
   controllers use it, or the **Meta Quest Touch Plus** profile if listed).
4. **XR Plug-in Management → Project Validation**: click **Fix All**
   on both tabs. Repeat until it's clean.
5. If Unity asks to enable the new Input System backend and restart, say yes.

## 3. Bootstrap scene (never unloaded)

**File → New Scene** (Basic URP), save as `Assets/XRPod/Scenes/Bootstrap.unity`.

1. Delete the default **Main Camera** (the XR Origin brings its own).
   Keep the Directional Light for now.
2. Drag in **XR Origin (XR Rig)** from
   `Assets/Samples/XR Interaction Toolkit/<version>/Starter Assets/Prefabs/`.
   It already has controller movement: left stick moves, right stick
   turns, plus teleport. Also drag in the **XR Interaction Setup** prefab
   if the sample has one; it includes the input actions manager.
3. **Zone probe:** expand XR Origin → Camera Offset → **Main Camera**.
   Right-click it → **Create Empty**, name it `ZoneProbe`. **Add Component
   → Player Zone Probe**. It adds a small trigger sphere and a kinematic
   Rigidbody for you.
4. **Create Empty** at the root, name it `XRPod`, and add:
   - **Vr System Root**: Start Environment = Forest, Pod Link = empty
     (offline), Sponsor Available and Sponsor Zone Tracking unticked
   - **Environment Scene Loader**: scene names Beach / Forest / Desert
   - **Editor Test Controls**
5. For testing without a headset, drag in the **XR Device Simulator**
   prefab from the samples. **Disable it before building for the Quest.**

## 4. Environment scenes

Create `Assets/XRPod/Scenes/Beach.unity`, `Forest.unity` and `Desert.unity`
(**File → New Scene → Basic URP**). In each one:

- **Delete the Main Camera.** The camera comes from Bootstrap. Two
  cameras means two "players".
- Add a **Plane** (GameObject → 3D Object → Plane) as ground, scaled up
  (e.g. 10, 1, 10), plus anything to make it recognisable (colour, a few
  cubes, skybox; Window → Rendering → Lighting sets the skybox per scene).
- Environment scenes become the active scene when loaded, so their
  lighting and skybox apply.

**File → Build Profiles → Scene List:** add **Bootstrap first**, then Beach,
Forest, Desert. A scene missing from this list can't be loaded.

## 5. Zones

In an environment scene, for each zone:

1. **GameObject → 3D Object → Cube**, name it with the zone's id from
   `ZONES.md`, e.g. `forest-clearing`.
   Scale it to cover the area, and make it **tall** (e.g. Y = 4) so the
   head-height probe is inside it.
2. Remove its **Mesh Renderer** (or keep it with a see-through material
   while you're testing).
3. On the **Box Collider**, tick **Is Trigger**.
4. **Add Component → Zone Volume**:
   - Zone Id: unique in this scene (defaults to the object's name)
   - Zone Type: Hot / Cool / Windy / Neutral
   - Environment: **the scene it's in** (Forest for Forest.unity)
   - Priority: 0, or higher for a zone nested inside another

Make at least two zones overlap in one scene so you can test that.

## 6. Test in the Editor (no headset)

Open **Bootstrap**, press **Play**. You should see the Forest load and a
status line top-left: `Environment: Forest / Zone: neutral`.

- Move with the **XR Device Simulator** (its on-screen help lists the
  keys; usually WASD plus right mouse to look).
- The app starts in the **waiting room** ("No world chosen yet"). **1 / 2 /
  3** switch Beach / Forest / Desert, **4** the sponsor's (a "coming soon"
  room until it's integrated, see `SPONSOR_INTEGRATION.md`), **0** back to
  the waiting room. **P** pretends the pod asked for one. While connected
  to the Pi, the HUD's pick wins.
- The Console logs every change, e.g.
  `[XRPod] [forest] zone forest-open (cool) -> forest-clearing (hot) (Entered)`.

Checklist:

- [ ] Walk into a zone: exactly one "Entered" log
- [ ] Walk out: one "Exited" log, zone back to the world's base zone
      (e.g. `forest-open`)
- [ ] Overlap two zones: the right one is active (priority, then newest);
      leaving the inner one falls back to the outer one
- [ ] Switch environment while inside a zone: the new scene loads, the old
      one is gone (Hierarchy shows Bootstrap + one scene), and the zone
      becomes the new world's base zone
- [ ] Spam 1/2/3 quickly: you end up in the last one you pressed, no errors
- [ ] "Last sent" on screen changes only when the zone/environment changes

## 7. Build for Meta Quest 3

1. **Headset:** enable Developer Mode in the Meta Horizon phone app
   (needs a Meta developer account/organisation). Connect by USB-C, and
   accept "Allow USB debugging" in the headset.
2. **File → Build Profiles →** select **Meta Quest** (or **Android**) →
   **Switch Platform** (slow the first time).
3. **Player Settings** (button in Build Profiles):
   - Company/Product name; Package name e.g. `edu.csus.xrpod`
   - **Other Settings → Allow downloads over HTTP: Always allowed**.
     The Pi serves plain HTTP; Android blocks it otherwise.
4. Run **Project Validation** again and **Fix All**.
5. **Disable the XR Device Simulator** object in Bootstrap.
6. **Build And Run** with the headset selected as Run Device. The app shows
   up in the headset's Library under **Unknown Sources**.

## 8. Connect to the Pi

The Pi's VR support and the HUD's environment picker are on `main` (see
`POD_PROTOCOL_PROPOSAL.md`). Without a Pi, Unity runs offline and only
the keyboard switches worlds.

1. In the Bootstrap scene, select the `XRPod` object → **Add Component →
   Http Pod Link**. Set **Base Url**:
   - testing on this PC: `http://localhost:8080`, with the Pi software
     running here (`python pi/agent.py` from the repo root; the HUD is then
     at `http://localhost:8080`)
   - the real Pi: its address, e.g. `http://10.199.194.129` on Zainab's
     hotspot (no port needed, the Pi uses 80). `xrpod.local` may not
     resolve on the Quest.
2. Drag the Http Pod Link component onto **Vr System Root → Pod Link**.
   (Empty Pod Link = offline.)
3. **Edit → Project Settings → Player → Other Settings → Allow downloads
   over HTTP: Always allowed.** The Pi serves plain HTTP.
4. Save, press **Play**, and pick an environment in the HUD: Unity should
   switch within ~1 s. Walk into zones: the HUD's VR line shows e.g.
   `VR: desert / desert-cave-inside (cool)` with a green dot.

On the headset, the Quest and the Pi must be on the same Wi-Fi. It has no
internet; that's fine.

## Switching worlds

The view fades to black, the new world loads, the user is moved to its
start spot, and the view fades back in (`ScreenFader`, set up by
Environment Scene Loader; **Fade Seconds** there). To choose the start
spot in a world, add an empty object on the floor with **Environment Spawn
Point**, facing where the user should look (a green marker shows it in the
Scene view). Without one, the user starts at the scene's origin facing +Z.

## Not done yet

- Changing the Pi's address in the headset without rebuilding the app.
- Real environment art, sound and zone layouts.
