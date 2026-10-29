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
  dotnet run --project unity/OfflineTests
  ```
  ```bash
  dotnet run --project unity/OfflineTests -- demo
  ```
- **Agree on `.gitignore` and Git LFS with the team before committing
  any Unity-generated files.** Two unmerged branches
  (`claude/compassionate-bohr-c1rd20`, `feature/iaq-scent-mqtt`) already
  have a `unity/.gitignore` and LFS rules in `.gitattributes`. Without
  them, `Library/` (gigabytes) and binary assets would end up in git. The
  scripts and docs on this branch are safe to commit now.

## 1. Create the project inside `unity/`

Unity Hub won't create a project in a folder that already has files, and
`unity/` already holds `Assets/XRPod/` and `OfflineTests/`.

1. Unity Hub → **New project** → template **Universal 3D** (URP). Name it
   `XRPodVR` and put it **outside** the repo, e.g. `C:\Users\<you>\XRPodVR`.
   Let it open once, then close Unity.
2. In File Explorer, copy from `XRPodVR` into the repo's `unity/` folder:
   - `Packages/` and `ProjectSettings/`
   - the **contents** of `XRPodVR/Assets/` into `unity/Assets/` (merge;
     keep our `Assets/XRPod/` folder)
3. Unity Hub → **Add** → **Add project from disk** → choose the repo's
   `unity/` folder. Open it with **6.6**. Delete the temporary `XRPodVR`.
4. **Edit → Project Settings → Editor**: Version Control mode **Visible Meta
   Files**, Asset Serialization **Force Text** (scenes merge as text).
5. Check the **Console** (Window → General → Console). Our scripts should
   compile with no errors. Unity creates a `.meta` file next to every
   script; commit them along with the scripts.

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

1. **GameObject → 3D Object → Cube**, name it e.g. `forest-clearing-wind`.
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
- **1 / 2 / 3** switch Beach / Forest / Desert. **4** selects the
  sponsor's experience (ignored until it's integrated, see
  `SPONSOR_INTEGRATION.md`). **P** pretends the pod asked for one.
- The Console logs every change, e.g.
  `[XRPod] [forest] zone neutral -> forest-clearing-wind (windy) (Entered)`.

Checklist:

- [ ] Walk into a zone: exactly one "Entered" log
- [ ] Walk out: one "Exited" log, zone back to neutral
- [ ] Overlap two zones: the right one is active (priority, then newest);
      leaving the inner one falls back to the outer one
- [ ] Switch environment while inside a zone: zone goes neutral, new scene
      loads, the old scene is gone (Hierarchy shows Bootstrap + one scene)
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

## 8. Connect to the Pi (later)

The Pi doesn't have the VR endpoints yet (see `POD_PROTOCOL_PROPOSAL.md`).
Once it does:

1. Add **Http Pod Link** to the `XRPod` object; set **Base Url** to the Pi's
   IP, e.g. `http://192.168.1.50`. `xrpod.local` may not resolve on the
   Quest.
2. Drag the `XRPod` object's Http Pod Link component into **Vr System Root
   → Pod Link**.
3. Quest and Pi on the same Wi-Fi. Pick an environment in the HUD; the
   headset should switch within ~1 s.

## Not done yet

- Spawn point per environment (the player keeps their position when
  switching).
- Fade to black during scene switches (more comfortable in VR).
- Real environment art, sound and zone layouts.
