// Turns a store pack's demo scene into one of our real ("v1") worlds:
// menu XRPod > Make Beach v1 / Make Forest v1 / Make Desert v1.
//
// It copies the pack's scene to Assets/XRPod/Scenes/<World>_v1.unity (the
// pack's own files aren't changed), then in the copy:
//   - removes the pack's cameras (ours comes from Bootstrap),
//   - turns off post-processing volumes (too slow on the Quest),
//   - adds a start spot where the pack's camera was,
//   - copies our zones from the test world, placed relative to that start
//     spot like in the test world, for you to line up by hand,
// and points Bootstrap's Environment Scene Loader at the new scene.
//
// v1 worlds are edited by hand. XRPod > Create Test Scenes never replaces
// them. The scene file goes in git; the pack's files don't (vr/.gitignore),
// so a teammate imports the pack from their own account to see it.

using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using XRPod.VR.Core;

namespace XRPod.VR
{
    static class XRPodWorldSetup
    {
        const string SceneFolder = "Assets/XRPod/Scenes";

        [MenuItem("XRPod/Make Beach v1 (from Beach - resort)")]
        static void MakeBeachV1() => MakeWorld(EnvironmentId.Beach, "Beach", "Assets/Beach - resort");

        // Forest and desert also get collision shapes straight away (the
        // beach gets them from XRPod > Finish Beach v1, after resizing).
        [MenuItem("XRPod/Make Forest v1 (from ForestVision)")]
        static void MakeForestV1() =>
            MakeWorld(EnvironmentId.Forest, "Forest", "Assets/ForestVision", "Sample1", addColliders: true);

        [MenuItem("XRPod/Make Desert v1 (from Raft on the desert)")]
        static void MakeDesertV1() =>
            MakeWorld(EnvironmentId.Desert, "Desert", "Assets/EmaceArt - raft on the desert", "DemoScene_New2026", addColliders: true);

        // ForestVision's grass is about as tall as a person, so it fills your
        // view (on the headset too, where your eyes are at your real height).
        // Shrinks every kind of grass and plant to at most knee height.
        // Changes a copy of the terrain (the pack's own stays as it was).
        [MenuItem("XRPod/Shorten Forest Grass")]
        static void ShortenForestGrass()
        {
            const float target = 0.8f; // metres, a bit above the knee
            var scene = SceneManager.GetActiveScene();
            if (scene.name != "Forest_v1")
            {
                EditorUtility.DisplayDialog("XRPod", "Open Forest_v1 first (Assets > XRPod > Scenes), then run this again.", "OK");
                return;
            }

            var kinds = 0;
            foreach (var root in scene.GetRootGameObjects())
            foreach (var terrain in root.GetComponentsInChildren<Terrain>(true))
            {
                // Always start again from the pack's original grass, so this
                // can be re-run with a different height.
                var data = XRPodWorldFit.CopyTerrainData(OriginalTerrain(terrain.terrainData), "Assets/ForestVision", scene.name);
                terrain.terrainData = data;
                var collider = terrain.GetComponent<TerrainCollider>();
                if (collider != null) collider.terrainData = data;

                var details = data.detailPrototypes;
                foreach (var detail in details)
                {
                    // A grass texture's height is in metres; a mesh's is a
                    // multiple of the mesh's own height.
                    var unit = detail.usePrototypeMesh ? MeshHeight(detail.prototype) : 1f;
                    var tallest = unit * detail.maxHeight;
                    if (tallest <= target) continue;
                    var f = target / tallest;
                    detail.minHeight *= f;
                    detail.maxHeight *= f;
                    kinds++;
                }
                data.detailPrototypes = details;
                data.RefreshPrototypes();
                EditorUtility.SetDirty(data);
            }

            // Grass placed as separate objects, not painted on the terrain.
            var objects = 0;
            foreach (var root in scene.GetRootGameObjects())
            foreach (var renderer in root.GetComponentsInChildren<MeshRenderer>(true))
            {
                var name = renderer.name.ToLowerInvariant();
                if (!(name.Contains("grass") || name.Contains("fern") || name.Contains("reed") || name.Contains("weed"))) continue;
                var height = renderer.bounds.size.y;
                if (height <= target || height > 4f) continue; // short already, or not grass
                Undo.RecordObject(renderer.transform, "Shorten forest grass");
                var s = renderer.transform.localScale;
                renderer.transform.localScale = new Vector3(s.x, s.y * target / height, s.z);
                objects++;
            }

            AssetDatabase.SaveAssets();
            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene);
            EditorUtility.DisplayDialog("XRPod",
                kinds + objects == 0
                    ? "All the grass is knee height or lower already: nothing changed."
                    : $"Set {kinds} kind(s) of terrain grass and {objects} grass object(s) to at most {target} m tall. Saved.",
                "OK");
        }

        // The pack's own terrain that Forest_v1 was copied from (the one its
        // Sample1 scene uses), or `current` if that can't be found.
        static TerrainData OriginalTerrain(TerrainData current)
        {
            foreach (var path in AssetDatabase.GetDependencies("Assets/ForestVision/Scenes/Sample1.unity", false))
            {
                var data = AssetDatabase.LoadAssetAtPath<TerrainData>(path);
                if (data != null) return data;
            }
            return current;
        }

        // Height of a detail mesh prefab, in metres (1 if it can't be measured).
        static float MeshHeight(GameObject prefab)
        {
            if (prefab == null) return 1f;
            var tallest = 0f;
            foreach (var mesh in prefab.GetComponentsInChildren<MeshFilter>(true))
                if (mesh.sharedMesh != null)
                    tallest = Mathf.Max(tallest, mesh.sharedMesh.bounds.size.y * Mathf.Abs(mesh.transform.lossyScale.y));
            return tallest > 0f ? tallest : 1f;
        }

        static void MakeWorld(EnvironmentId environment, string world, string packFolder,
            string sceneName = null, bool addColliders = false)
        {
            if (EditorApplication.isPlayingOrWillChangePlaymode)
            {
                EditorUtility.DisplayDialog("XRPod", "Stop Play mode first.", "OK");
                return;
            }
            var source = FindScene(packFolder, sceneName);
            if (source == null)
            {
                EditorUtility.DisplayDialog("XRPod",
                    $"No {(sceneName ?? "scene")} found in {packFolder}. Import the pack first.", "OK");
                return;
            }
            var target = $"{SceneFolder}/{world}_v1.unity";
            if (File.Exists(target) && !EditorUtility.DisplayDialog("XRPod",
                    $"{world}_v1 already exists. Replace it with a fresh copy of the pack's scene? " +
                    "Anything you changed in it (e.g. zones you lined up) will be lost.", "Replace", "Cancel"))
                return;
            if (!EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo()) return;

            if (File.Exists(target)) AssetDatabase.DeleteAsset(target);
            if (!AssetDatabase.CopyAsset(source, target))
            {
                EditorUtility.DisplayDialog("XRPod", $"Couldn't copy {source}.", "OK");
                return;
            }

            var scene = EditorSceneManager.OpenScene(target, OpenSceneMode.Single);
            var start = RemoveCameras(scene, out var removedCameras);
            var volumes = TurnOffVolumes(scene);
            // Before finding the ground below: it may need a collider to be found.
            var colliders = addColliders ? XRPodWorldFit.AddColliders(scene) : 0;
            Physics.SyncTransforms();

            // Start spot on the ground under where the pack's camera was,
            // facing the same way.
            var spawn = new GameObject("Player start").AddComponent<EnvironmentSpawnPoint>().transform;
            var ground = Physics.Raycast(start.position + Vector3.up, Vector3.down, out var hit, 500f);
            spawn.position = ground ? hit.point : new Vector3(start.position.x, 0f, start.position.z);
            spawn.rotation = Quaternion.Euler(0f, start.rotation.eulerAngles.y, 0f);
            if (!ground)
            {
                // Nothing to stand on under the start spot: an invisible floor
                // so the VR player doesn't fall.
                var floor = GameObject.CreatePrimitive(PrimitiveType.Plane);
                floor.name = "Floor (invisible)";
                floor.transform.position = spawn.position;
                floor.transform.localScale = new Vector3(30f, 1f, 30f);
                floor.GetComponent<Renderer>().enabled = false;
            }

            var zonesCopied = CopyZones(world, scene, spawn);
            EditorSceneManager.SaveScene(scene);

            AddToBuild(target);
            PointLoaderAt(environment, $"{world}_v1");

            EditorSceneManager.OpenScene(target, OpenSceneMode.Single);
            EditorUtility.DisplayDialog("XRPod",
                $"{world}_v1 is ready and the app now uses it for {world}.\n\n" +
                $"Removed {removedCameras} camera(s), turned off {volumes} post-processing volume(s), " +
                (addColliders ? $"added collision shapes to {colliders} object(s), " : "") +
                $"added a start spot{(ground ? "" : " and an invisible floor")}" +
                (zonesCopied ? ", and copied the zones from the test world.\n\n" : ".\n\nNo test world zones found: run XRPod > Create Test Scenes, then this again.\n\n") +
                "Next: in the Hierarchy open 'Zones', and move and scale each zone box to fit the scenery " +
                "(e.g. beach-waterline along the water). Press Z in Play mode to see the zone pads.",
                "OK");
        }

        // Removes every camera (and its audio listener). Returns where the
        // first one was, for the start spot.
        static Pose RemoveCameras(Scene scene, out int removed)
        {
            removed = 0;
            var where = new Pose(Vector3.zero, Quaternion.identity);
            foreach (var root in scene.GetRootGameObjects())
            {
                foreach (var camera in root.GetComponentsInChildren<Camera>(true))
                {
                    if (camera == null) continue; // went with an object removed above
                    if (removed == 0) where = new Pose(camera.transform.position, camera.transform.rotation);
                    removed++;
                    // A camera object without children goes. One that holds
                    // other objects keeps them and loses all its own parts.
                    // (Unity won't remove a Camera while URP's camera data,
                    // which requires it, is still on the object, so the
                    // parts go in reverse order, repeated until none are left.)
                    var holder = camera.gameObject;
                    if (holder.transform.childCount == 0)
                    {
                        Object.DestroyImmediate(holder);
                        continue;
                    }
                    for (var pass = 0; pass < 4; pass++)
                    {
                        var parts = holder.GetComponents<Component>();
                        for (var i = parts.Length - 1; i >= 0; i--)
                            if (!(parts[i] is Transform)) Object.DestroyImmediate(parts[i]);
                    }
                    holder.name += " (camera removed)";
                }
            }
            return where;
        }

        // Post-processing (a "Volume", e.g. Global Volume) costs too much on
        // the Quest. Found by type name so this doesn't depend on the
        // render pipeline's code.
        static int TurnOffVolumes(Scene scene)
        {
            var count = 0;
            foreach (var root in scene.GetRootGameObjects())
            foreach (var component in root.GetComponentsInChildren<Component>(true))
            {
                if (component == null || component.GetType().Name != "Volume" || !component.gameObject.activeSelf) continue;
                component.gameObject.SetActive(false);
                count++;
            }
            return count;
        }

        // Copies the test world's "Zones" into the new scene, moved and turned
        // so they sit around the new start spot the way they sit around the
        // test world's start (at its origin, facing +z).
        static bool CopyZones(string world, Scene target, Transform spawn)
        {
            var testPath = $"{SceneFolder}/{world}.unity";
            if (!File.Exists(testPath)) return false;
            var test = EditorSceneManager.OpenScene(testPath, OpenSceneMode.Additive);
            GameObject zones = null;
            foreach (var root in test.GetRootGameObjects())
                if (root.name == "Zones") zones = root;
            // Decided now: once the test scene closes, Unity reports its
            // objects as null even though the copy was made.
            var copied = zones != null;
            if (copied)
            {
                var copy = Object.Instantiate(zones);
                copy.name = "Zones";
                SceneManager.MoveGameObjectToScene(copy, target);
                copy.transform.SetPositionAndRotation(spawn.position, spawn.rotation);
            }
            EditorSceneManager.CloseScene(test, true);
            return copied;
        }

        static void AddToBuild(string path)
        {
            var scenes = new System.Collections.Generic.List<EditorBuildSettingsScene>(EditorBuildSettings.scenes);
            if (scenes.Exists(s => s.path == path)) return;
            scenes.Add(new EditorBuildSettingsScene(path, true));
            EditorBuildSettings.scenes = scenes.ToArray();
        }

        // Sets the scene Bootstrap's Environment Scene Loader loads for this
        // environment.
        static void PointLoaderAt(EnvironmentId environment, string sceneName)
        {
            var scene = EditorSceneManager.OpenScene($"{SceneFolder}/Bootstrap.unity", OpenSceneMode.Single);
            foreach (var root in scene.GetRootGameObjects())
            {
                var loader = root.GetComponentInChildren<EnvironmentSceneLoader>();
                if (loader == null) continue;
                var settings = new SerializedObject(loader);
                var list = settings.FindProperty("scenes");
                var found = false;
                for (var i = 0; i < list.arraySize; i++)
                {
                    var entry = list.GetArrayElementAtIndex(i);
                    if (entry.FindPropertyRelative("environment").intValue != (int)environment) continue;
                    entry.FindPropertyRelative("sceneName").stringValue = sceneName;
                    found = true;
                }
                if (!found)
                {
                    list.arraySize++;
                    var entry = list.GetArrayElementAtIndex(list.arraySize - 1);
                    entry.FindPropertyRelative("environment").intValue = (int)environment;
                    entry.FindPropertyRelative("sceneName").stringValue = sceneName;
                }
                settings.ApplyModifiedPropertiesWithoutUndo();
            }
            EditorSceneManager.SaveScene(scene);
        }

        // The pack's scene with this name, or its first scene if no name is given.
        static string FindScene(string folder, string name)
        {
            if (!AssetDatabase.IsValidFolder(folder)) return null;
            foreach (var guid in AssetDatabase.FindAssets("t:Scene", new[] { folder }))
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                if (name == null || Path.GetFileNameWithoutExtension(path) == name) return path;
            }
            return null;
        }
    }
}
