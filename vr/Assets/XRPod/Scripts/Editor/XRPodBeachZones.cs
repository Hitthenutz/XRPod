// Places the beach zones (vr/docs/ZONES.md) to fit Beach_v1's scenery:
// menu XRPod > Auto Place Beach Zones. Run it with Beach_v1 open.
//
// From the start spot it looks for the nearest shoreline (where the terrain
// dips below the water), then puts:
//   beach-shore       on the sand just before the water (13 m deep)
//   beach-waterline   where sand meets sea (from 3 m on the sand to 4 m in)
//   beach-palm-shade  under the nearest palm tree (or umbrella)
//   beach-dunes       on the highest sand nearby, away from the water
//   beach-open        over the whole beach
// plus an invisible floor just under the water, so the user can wade in a
// little but not walk under the sea.
// Each zone sits on the ground there and is tall enough for the user's
// head. Run it again any time; move zones by hand afterwards if you like.

using System.Collections.Generic;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace XRPod.VR
{
    static class XRPodBeachZones
    {
        const float ShoreWidth = 60f;

        [MenuItem("XRPod/Auto Place Beach Zones")]
        static void AutoPlaceMenu() => AutoPlace(null);

        // One click to make Beach_v1 walkable and real-sized: scales the
        // scenery so umbrellas are real size, gives scenery colliders so the
        // user can't walk through it, then places the zones (below).
        [MenuItem("XRPod/Finish Beach v1 (real size, collisions, zones)")]
        static void Finish()
        {
            var scene = SceneManager.GetActiveScene();
            if (EditorApplication.isPlayingOrWillChangePlaymode || scene.name != "Beach_v1")
            {
                EditorUtility.DisplayDialog("XRPod", "Stop Play mode and open Beach_v1 first " +
                    "(Assets > XRPod > Scenes > Beach_v1).", "OK");
                return;
            }
            var sized = XRPodWorldFit.FitToRealSize(scene, "umbrella", 2.3f, "Assets/Beach - resort/Terrain");
            var colliders = XRPodWorldFit.AddColliders(scene);
            AutoPlace($"{sized}\nAdded collision shapes to {colliders} object(s), so you can't walk through them " +
                      "(small things like toys you step over).\n\n");
        }

        // A bit bigger each click, if the beach still feels small. Zones are
        // re-placed to match.
        [MenuItem("XRPod/Make Beach v1 15% Bigger")]
        static void Bigger()
        {
            var scene = SceneManager.GetActiveScene();
            if (EditorApplication.isPlayingOrWillChangePlaymode || scene.name != "Beach_v1")
            {
                EditorUtility.DisplayDialog("XRPod", "Stop Play mode and open Beach_v1 first " +
                    "(Assets > XRPod > Scenes > Beach_v1).", "OK");
                return;
            }
            XRPodWorldFit.ScaleWorld(scene, 1.15f, "Assets/Beach - resort/Terrain");
            var now = XRPodWorldFit.MeasuredHeight(scene, "umbrella");
            AutoPlace($"Made the beach 15% bigger: umbrellas are now about {now:0.0} m tall.\n\n");
        }

        static void AutoPlace(string before)
        {
            var scene = SceneManager.GetActiveScene();
            if (EditorApplication.isPlayingOrWillChangePlaymode || scene.name != "Beach_v1")
            {
                EditorUtility.DisplayDialog("XRPod", "Stop Play mode and open Beach_v1 first " +
                    "(Assets > XRPod > Scenes > Beach_v1).", "OK");
                return;
            }

            var spawn = Find<EnvironmentSpawnPoint>(scene);
            var terrain = Find<Terrain>(scene);
            var water = FindWater(scene);
            var zones = ZonesById(scene);
            if (spawn == null || terrain == null || water == null || zones.Count == 0)
            {
                EditorUtility.DisplayDialog("XRPod",
                    $"Missing: {(spawn == null ? "start spot " : "")}{(terrain == null ? "terrain " : "")}" +
                    $"{(water == null ? "water " : "")}{(zones.Count == 0 ? "zones" : "")}. " +
                    "Run XRPod > Make Beach v1 first.", "OK");
                return;
            }

            var waterY = water.bounds.center.y;
            float Ground(Vector3 p) => terrain.SampleHeight(p) + terrain.transform.position.y;
            var start = spawn.transform.position;

            // Nearest shore: walk out in 72 directions until the sand is
            // under the water.
            var bestDistance = float.MaxValue;
            var toSea = Vector3.forward;
            for (var i = 0; i < 72; i++)
            {
                var direction = Quaternion.Euler(0f, i * 5f, 0f) * Vector3.forward;
                for (var d = 1f; d < 200f; d += 0.5f)
                {
                    if (Ground(start + direction * d) >= waterY) continue;
                    if (d < bestDistance)
                    {
                        bestDistance = d;
                        toSea = direction;
                    }
                    break;
                }
            }
            if (bestDistance == float.MaxValue)
            {
                EditorUtility.DisplayDialog("XRPod", "Couldn't find where the sand meets the water within 200 m " +
                    "of the start spot. Place the zones by hand.", "OK");
                return;
            }

            var facing = Quaternion.LookRotation(toSea, Vector3.up);
            var shorePoint = start + toSea * bestDistance;
            Undo.SetCurrentGroupName("Auto place beach zones");

            // Shore: 13 m of sand before the water. Waterline: 3 m of sand
            // and 4 m of water.
            Place(zones, "beach-shore", start + toSea * (bestDistance - 6.5f), facing, ShoreWidth, 13f, Ground);
            Place(zones, "beach-waterline", shorePoint + toSea * 0.5f, facing, ShoreWidth, 7f,
                p => Mathf.Min(Ground(p), waterY));

            // Shade: under the nearest palm (a terrain tree), else umbrella.
            var shade = NearestPalm(terrain, start) ?? NearestNamed(scene, "umbrella", start);
            if (shade.HasValue)
                Place(zones, "beach-palm-shade", shade.Value, facing, 4f, 4f, Ground);

            var umbrellas = AddUmbrellaShade(scene, zones, Ground);
            before = (before ?? "") + $"Shade zones under {umbrellas} umbrella(s).\n";

            // Dunes: the highest sand within 30 m that's well away from the water.
            var dune = start;
            var duneHeight = float.MinValue;
            for (var x = -30f; x <= 30f; x += 2f)
            for (var z = -30f; z <= 30f; z += 2f)
            {
                var p = start + new Vector3(x, 0f, z);
                if (Vector3.Dot(p - start, toSea) > bestDistance - 15f) continue; // too near the sea
                var h = Ground(p);
                if (h > duneHeight)
                {
                    duneHeight = h;
                    dune = p;
                }
            }
            Place(zones, "beach-dunes", dune, facing, 8f, 8f, Ground);

            // Everything else: the whole beach, from below the water to well
            // above the highest sand.
            if (zones.TryGetValue("beach-open", out var open))
            {
                Undo.RecordObject(open.transform, "Auto place beach zones");
                open.transform.SetPositionAndRotation(new Vector3(start.x, waterY - 5f, start.z), facing);
                var box = open.GetComponent<BoxCollider>();
                Undo.RecordObject(box, "Auto place beach zones");
                box.center = new Vector3(0f, 25f, 0f);
                box.size = new Vector3(300f, 50f, 300f);
            }

            AddShallowWaterFloor(scene, start, waterY);
            EditorSceneManager.MarkSceneDirty(scene);
            EditorUtility.DisplayDialog("XRPod", (before ?? "") +
                $"Zones placed. The nearest water is {bestDistance:0} m from the start spot.\n\n" +
                "Save (Ctrl + S), then open Bootstrap, press Play and 1, and press Z to see the zone pads. " +
                "Ctrl + Z undoes this.", "OK");
        }

        // A shade zone under every umbrella, all with one id so the Pi needs
        // one recipe (vr/docs/ZONES.md). Sized to the canopy; priority 15:
        // shade beats the sunny shore (10), the waterline's wind (20) beats
        // shade. Old ones are removed first, so this can run again after
        // resizing. Returns how many umbrellas got one.
        static int AddUmbrellaShade(Scene scene, Dictionary<string, GameObject> zones, System.Func<Vector3, float> ground)
        {
            const string id = "beach-umbrella-shade";
            Transform parent = null;
            foreach (var zone in zones.Values)
            {
                parent = zone.transform.parent;
                break;
            }
            foreach (var old in Object.FindObjectsByType<ZoneVolume>(FindObjectsInactive.Include))
                if (old.name == id && old.gameObject.scene == scene) Undo.DestroyObjectImmediate(old.gameObject);

            var padMaterial = AssetDatabase.LoadAssetAtPath<Material>("Assets/XRPod/Materials/Zone cool 10.mat");
            var sun = SunDirection(scene);
            var placed = new List<Vector3>();
            foreach (var root in scene.GetRootGameObjects())
            foreach (var renderer in root.GetComponentsInChildren<Renderer>())
            {
                if (!renderer.name.ToLowerInvariant().Contains("umbrella")) continue;
                var canopy = renderer.bounds;
                var under = new Vector3(canopy.center.x, 0f, canopy.center.z);
                if (placed.Exists(p => Vector3.Distance(p, under) < 1f)) continue; // same umbrella, another part
                placed.Add(under);
                // The shade is where the shadow falls, which is off to one
                // side when the sun isn't straight overhead.
                var spot = ShadowSpot(canopy.center, ground(under), sun);

                var shade = new GameObject(id);
                Undo.RegisterCreatedObjectUndo(shade, "Auto place beach zones");
                if (parent != null) shade.transform.SetParent(parent, true);
                else SceneManager.MoveGameObjectToScene(shade, scene);
                shade.transform.SetPositionAndRotation(new Vector3(spot.x, ground(spot), spot.z), Quaternion.identity);

                var box = shade.AddComponent<BoxCollider>();
                box.isTrigger = true;
                box.center = new Vector3(0f, 1.5f, 0f);
                box.size = new Vector3(canopy.size.x * 1.2f, 5f, canopy.size.z * 1.2f); // shadows stretch a little

                var volume = new SerializedObject(shade.AddComponent<ZoneVolume>());
                volume.FindProperty("zoneId").stringValue = id;
                volume.FindProperty("zoneType").intValue = (int)Core.ZoneType.Cool;
                volume.FindProperty("environment").intValue = (int)Core.EnvironmentId.Beach;
                volume.FindProperty("priority").intValue = 15;
                volume.ApplyModifiedPropertiesWithoutUndo();

                // The pad that shows the zone when Z is pressed.
                var pad = GameObject.CreatePrimitive(PrimitiveType.Cube);
                pad.name = "Marker";
                Object.DestroyImmediate(pad.GetComponent<Collider>());
                pad.transform.SetParent(shade.transform, false);
                pad.transform.localPosition = new Vector3(0f, 0.06f, 0f);
                pad.transform.localScale = new Vector3(canopy.size.x, 0.02f, canopy.size.z);
                if (padMaterial != null) pad.GetComponent<Renderer>().sharedMaterial = padMaterial;
            }
            return placed.Count;
        }

        // The way the scene's sunlight travels (its brightest directional
        // light), or straight down if there isn't one.
        static Vector3 SunDirection(Scene scene)
        {
            Light best = null;
            foreach (var root in scene.GetRootGameObjects())
            foreach (var light in root.GetComponentsInChildren<Light>())
                if (light.type == LightType.Directional && light.enabled && (best == null || light.intensity > best.intensity))
                    best = light;
            return best != null ? best.transform.forward : Vector3.down;
        }

        // Where on the ground (height groundY) the shadow of point p falls.
        // Capped at 6 m away, for a very low sun.
        static Vector3 ShadowSpot(Vector3 p, float groundY, Vector3 sun)
        {
            var below = new Vector3(p.x, 0f, p.z);
            if (sun.y > -0.05f) return below; // sun at or under the horizon: no useful shadow
            var t = (groundY - p.y) / sun.y;
            var offset = new Vector3(sun.x * t, 0f, sun.z * t);
            return below + Vector3.ClampMagnitude(offset, 6f);
        }

        // An invisible floor 0.4 m under the water's surface: the user can
        // wade in a little but never walk under the sea (the sand keeps
        // sloping down there). Works for the desktop walker and the VR
        // player alike. Replaced if it's already there.
        static void AddShallowWaterFloor(Scene scene, Vector3 start, float waterY)
        {
            const string name = "Shallow water floor (invisible)";
            foreach (var root in scene.GetRootGameObjects())
                if (root.name == name) Undo.DestroyObjectImmediate(root);
            var floor = GameObject.CreatePrimitive(PrimitiveType.Plane);
            floor.name = name;
            SceneManager.MoveGameObjectToScene(floor, scene);
            floor.transform.position = new Vector3(start.x, waterY - 0.4f, start.z);
            floor.transform.localScale = new Vector3(60f, 1f, 60f); // 600 x 600 m
            Object.DestroyImmediate(floor.GetComponent<Renderer>());
            Object.DestroyImmediate(floor.GetComponent<MeshFilter>());
            Undo.RegisterCreatedObjectUndo(floor, "Auto place beach zones");
        }

        // Moves a zone to sit on the ground at `center`, facing the sea,
        // `width` x `depth` m and tall enough for the user's head.
        static void Place(Dictionary<string, GameObject> zones, string id, Vector3 center, Quaternion facing,
            float width, float depth, System.Func<Vector3, float> ground)
        {
            if (!zones.TryGetValue(id, out var zone)) return;
            Undo.RecordObject(zone.transform, "Auto place beach zones");
            zone.transform.SetPositionAndRotation(new Vector3(center.x, ground(center), center.z), facing);
            zone.transform.localScale = Vector3.one;

            var box = zone.GetComponent<BoxCollider>();
            Undo.RecordObject(box, "Auto place beach zones");
            box.center = new Vector3(0f, 1.5f, 0f); // from 1 m below the ground to 4 m above
            box.size = new Vector3(width, 5f, depth);

            var pad = zone.transform.Find("Marker");
            if (pad != null)
            {
                Undo.RecordObject(pad, "Auto place beach zones");
                pad.localPosition = new Vector3(0f, 0.05f, 0f);
                pad.localRotation = Quaternion.identity;
                pad.localScale = new Vector3(width, 0.02f, depth);
            }
        }

        static Vector3? NearestPalm(Terrain terrain, Vector3 from)
        {
            var data = terrain.terrainData;
            Vector3? best = null;
            var bestDistance = 40f; // only palms reasonably near the start
            foreach (var tree in data.treeInstances)
            {
                var p = Vector3.Scale(tree.position, data.size) + terrain.transform.position;
                var d = Vector3.Distance(new Vector3(p.x, from.y, p.z), from);
                if (d < bestDistance)
                {
                    bestDistance = d;
                    best = p;
                }
            }
            return best;
        }

        static Vector3? NearestNamed(Scene scene, string part, Vector3 from)
        {
            Vector3? best = null;
            var bestDistance = 40f;
            foreach (var root in scene.GetRootGameObjects())
            foreach (var child in root.GetComponentsInChildren<Transform>(true))
            {
                if (!child.name.ToLowerInvariant().Contains(part)) continue;
                var d = Vector3.Distance(child.position, from);
                if (d < bestDistance)
                {
                    bestDistance = d;
                    best = child.position;
                }
            }
            return best;
        }

        static Renderer FindWater(Scene scene)
        {
            foreach (var root in scene.GetRootGameObjects())
            foreach (var renderer in root.GetComponentsInChildren<Renderer>(true))
            {
                var name = renderer.name.ToLowerInvariant();
                if (name.Contains("water") || name.Contains("ocean") || name.Contains("sea")) return renderer;
            }
            return null;
        }

        static Dictionary<string, GameObject> ZonesById(Scene scene)
        {
            var zones = new Dictionary<string, GameObject>();
            foreach (var root in scene.GetRootGameObjects())
            foreach (var zone in root.GetComponentsInChildren<ZoneVolume>(true))
                zones[zone.name] = zone.gameObject;
            return zones;
        }

        static T Find<T>(Scene scene) where T : Component
        {
            foreach (var root in scene.GetRootGameObjects())
            {
                var found = root.GetComponentInChildren<T>(true);
                if (found != null) return found;
            }
            return null;
        }
    }
}
