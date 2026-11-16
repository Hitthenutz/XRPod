# Third-party assets in the VR app

Everything listed here is free. Add a line whenever you add someone
else's file. CC0 needs no credit, but listing it keeps track of where
things came from; CC BY assets **must** be credited here.

Assets under the Unity Asset Store or Fab licences must **not** be
committed (keep them in a git-ignored folder; each teammate imports
them from their own account).

## Store packs (not in git: import them yourself)

| Pack | Used for | Where it goes | Licence |
|---|---|---|---|
| [Beach - resort](https://assetstore.unity.com/) by Mixall (free) | `Beach_v1` scenery | `Assets/Beach - resort/` | Standard Unity Asset Store EULA |
| [Rain Forest SFX](https://assetstore.unity.com/) by Kedfa (free) | Forest rain and bird sounds | `Assets/Rain Forest SFX/` | Standard Unity Asset Store EULA |
| [Fantasy Forest Environment Free Sample](https://assetstore.unity.com/packages/3d/environments/fantasy/fantasy-forest-environment-free-demo-35361) (free) | `Forest_v1` trees and ground | `Assets/Fantasy Forest Environment Free Sample/` | Standard Unity Asset Store EULA |
| ForestVision by Bauervision (free) | Trying out for `Forest_v1` | `Assets/ForestVision/` | Standard Unity Asset Store EULA |
| Raft on the desert - Free Low Poly Pack by EmaceArt (free) | `Desert_v1` scenery | `Assets/EmaceArt - raft on the desert/` | Standard Unity Asset Store EULA |

To see a v1 world, add the pack to your Unity account (free ones too), then
**Window → Package Manager → My Assets → Download → Import**.

## In `Assets/XRPod/Environments/`

All from [Poly Haven](https://polyhaven.com), [CC0](https://polyhaven.com/license)
(public domain: no credit required). The 360 photos were scaled from 8K
to 4K for the Quest, and each roughness map was turned into a URP
smoothness map (`*_metal_smooth_2k.png`).

| World | File(s) | Asset | Author |
|---|---|---|---|
| Beach | `secluded_beach_sky_4k.jpg` | [Secluded Beach](https://polyhaven.com/a/secluded_beach) (360 photo, tonemapped JPG) | Poly Haven |
| Beach | `aerial_beach_01_*` | [Aerial Beach 01](https://polyhaven.com/a/aerial_beach_01) (2K textures) | Poly Haven |
| Forest | `mossy_forest_sky_4k.jpg` | [Mossy Forest](https://polyhaven.com/a/mossy_forest) (360 photo, tonemapped JPG) | Greg Zaal |
| Forest | `forest_leaves_02_*` | [Forest Leaves 02](https://polyhaven.com/a/forest_leaves_02) (2K textures) | Poly Haven |
| Desert | `goegap_sky_4k.jpg` | [Goegap](https://polyhaven.com/a/goegap) (360 photo, tonemapped JPG) | Poly Haven |
| Desert | `gravelly_sand_*` | [Gravelly Sand](https://polyhaven.com/a/gravelly_sand) (2K textures) | Poly Haven |
