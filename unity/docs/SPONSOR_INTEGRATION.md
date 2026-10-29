# Sponsor environment: integration plan

The sponsor is giving us an existing Unity environment. The goal is **one
XRPod app with four selectable experiences**: Beach, Forest, Desert and
the sponsor's, all switched from the HUD. This only works if their files
turn out to be compatible with our project.

**Status:** we haven't received or inspected anything yet. No sponsor files
are in the repo, and nothing below has been tried.

## What's ready in our code

| Piece | State |
|---|---|
| `EnvironmentId.Sponsor`, wire name `"sponsor"` | Done, tested offline |
| **Available** switch: selecting Sponsor is ignored (and logged) until it's ticked | Done, tested offline. VrSystemRoot → *Sponsor Available*, off by default |
| **Zone tracking** switch: zones are ignored in Sponsor until it's ticked; the Pi is told `zone_tracking: false` | Done, tested offline. VrSystemRoot → *Sponsor Zone Tracking*, off by default |
| Switching Sponsor ↔ Beach/Forest/Desert in any order | Done, tested offline |
| Scene to load for Sponsor | `EnvironmentSceneLoader` has a Sponsor row with an **empty** scene name, to fill in later |
| Key **4** in the Editor | Selects Sponsor (if available) |

Beach, Forest and Desert are unaffected: they're always available, with
zone tracking on.

## Step 1: inspect before importing anything

Unzip their delivery **outside** our repo and open it in its own Unity
project (or read the files). Write down:

| Check | Where to look | Why it matters |
|---|---|---|
| Unity version | `ProjectSettings/ProjectVersion.txt` | Much older projects may need upgrading; much newer can't open in 6.6 |
| Render pipeline | `Packages/manifest.json` (`com.unity.render-pipelines.universal`?), Project Settings → Graphics | We use **URP**. Built-in or HDRP materials render pink and need converting (HDRP isn't supported on Quest) |
| XR setup | `manifest.json`: `com.unity.xr.openxr`, `com.unity.xr.oculus` (Oculus XR plugin), `com.meta.xr.sdk.*` (Meta XR SDK), `com.unity.xr.interaction.toolkit` | Two XR plugins or rigs fighting is the most likely problem |
| Input | Project Settings → Player → Active Input Handling; `com.unity.inputsystem` | We use the new Input System |
| Their own camera/XR rig | Their scenes' Hierarchy | Our Bootstrap already has the XR Origin; two rigs = two cameras |
| Scripts | `Assets/**/*.cs`, `.asmdef` files | Look for `SceneManager.LoadScene(...)` *without* `Additive`, which would unload our Bootstrap; `DontDestroyOnLoad`; singletons; hard-coded scene names |
| Other packages / plugins | `manifest.json`, `Assets/Plugins/` | Versions that clash with ours; native plugins that don't support Android/Quest |
| Size, and how it's delivered | Folder size; `.unitypackage` vs. whole project vs. scenes | Git LFS needs; what's easiest to import |
| Licence / sharing terms | Ask the sponsor | Can it go in our (public?) GitHub repo? |

Also check whether **this repo is public**. If it is, ask the sponsor before
committing their files. They may need to stay out of git (e.g. listed in
`.gitignore` and shared another way).

## Step 2: import, without editing their files

- Put their content in its own folder: `Assets/Sponsor/` (keep their
  internal structure inside it). Don't rename, move or edit files in it,
  so a newer delivery can replace the folder cleanly.
- Install any packages it needs that we don't have, with the team's
  agreement, and check our three scenes still work.
- Add their scene(s) to **Build Profiles → Scene List**.

## Step 3: connect it to XRPod

Pick whichever fits what we find:

- **A. Their scene loads as-is.** Set the Sponsor row in
  `EnvironmentSceneLoader` to their scene's name. Works if the scene has no
  camera/XR rig of its own and doesn't load other scenes itself.
- **B. Our own wrapper scene** (`Assets/XRPod/Scenes/SponsorEntry.unity`)
  that contains their environment as a prefab or with their objects
  dragged in, and with their camera/rig left out. Use this if their scene
  carries a rig, managers we don't want, or needs extra setup. Their
  original scene stays untouched.
- **C. Needs code changes on our side**, e.g. their content is split over
  several scenes that must load together. Extend `EnvironmentSceneLoader`
  then; the Core logic doesn't change.

Then tick **VrSystemRoot → Sponsor Available**.

## Step 4: zones (optional)

Only if adding our own objects to their environment is fine with the
sponsor:

1. In our wrapper scene (option B) or a small additive scene of our own,
   add `ZoneVolume`s with Environment = **Sponsor**. Don't add them inside
   their original scene files.
2. Tick **VrSystemRoot → Sponsor Zone Tracking**.

Until then, the Pi gets `zone_tracking: false` for Sponsor and can treat
it differently (e.g. keep the HUD's manual settings in automatic mode).

## Step 5: test

- [ ] 1/2/3/4 in the Editor: every switch works, in any order, with no errors
- [ ] Only one camera and one XR rig in the Hierarchy while in Sponsor
- [ ] Bootstrap is still loaded after entering and leaving Sponsor
- [ ] Our three environments still look and behave the same
- [ ] On the Quest: frame rate in Sponsor is smooth (it may need
      optimising for mobile)
- [ ] With Sponsor Zone Tracking off, the overlay shows "tracking off"
