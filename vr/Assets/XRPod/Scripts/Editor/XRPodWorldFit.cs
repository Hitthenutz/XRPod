// Helpers that make a store pack's scene fit the user in VR (used by
// XRPod > Finish Beach v1):
//   FitToRealSize  scales the whole world so a reference prop (e.g.
//                  umbrellas) is real size. Packs are often modelled small,
//                  which makes the user feel like a giant, on the headset too.
//   AddColliders   gives scenery without a collider a mesh collider, so the
//                  user can't walk through it.

using System.Collections.Generic;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace XRPod.VR
{
    static class XRPodWorldFit
    {
        // Our own objects, which are placed in real metres already.
        static bool IsOurs(GameObject root) =>
            root.GetComponentInChildren<ZoneVolume>(true) != null
            || root.GetComponent<EnvironmentSpawnPoint>() != null
            || root.name.Contains("(invisible)");

        // Scales everything (around the start spot) so the reference props
        // average realHeight metres tall. The terrain is copied first (into
        // copyFolder, kept out of git with the pack) because scaling changes
        // its data, and the pack's own terrain stays as it was. Returns a
        // sentence for the user.
        public static string FitToRealSize(Scene scene, string reference, float realHeight, string copyFolder)
        {
            var heights = new List<float>();
            foreach (var root in scene.GetRootGameObjects())
            foreach (var renderer in root.GetComponentsInChildren<Renderer>(true))
                if (renderer.name.ToLowerInvariant().Contains(reference)) heights.Add(renderer.bounds.size.y);
            if (heights.Count == 0) return $"No {reference}s found to measure, so the size wasn't changed.";
            heights.Sort();
            var measured = heights[heights.Count / 2];
            var factor = Mathf.Clamp(realHeight / measured, 1f, 4f);
            if (factor < 1.1f) return $"The {reference}s are {measured:0.0} m tall, real size already.";

            ScaleWorld(scene, factor, copyFolder);
            return $"The {reference}s were {measured:0.0} m tall, so the whole beach was made {factor:0.0}x bigger " +
                   $"(now about {realHeight} m).";
        }

        // Median height of the reference props, in metres (0 if none).
        public static float MeasuredHeight(Scene scene, string reference)
        {
            var heights = new List<float>();
            foreach (var root in scene.GetRootGameObjects())
            foreach (var renderer in root.GetComponentsInChildren<Renderer>(true))
                if (renderer.name.ToLowerInvariant().Contains(reference)) heights.Add(renderer.bounds.size.y);
            if (heights.Count == 0) return 0f;
            heights.Sort();
            return heights[heights.Count / 2];
        }

        // Scales everything except our own objects by `factor` around the
        // start spot, terrain included (via a copy of its data in copyFolder).
        public static void ScaleWorld(Scene scene, float factor, string copyFolder)
        {
            var spawn = Object.FindAnyObjectByType<EnvironmentSpawnPoint>();
            var pivot = spawn != null ? spawn.transform.position : Vector3.zero;
            Vector3 Scaled(Vector3 p) => pivot + (p - pivot) * factor;

            // Terrain: remember where it should end up, then scale its data.
            var terrains = new List<(Terrain terrain, Vector3 position)>();
            foreach (var root in scene.GetRootGameObjects())
            foreach (var terrain in root.GetComponentsInChildren<Terrain>(true))
                terrains.Add((terrain, Scaled(terrain.transform.position)));

            foreach (var root in scene.GetRootGameObjects())
            {
                if (IsOurs(root) || root.GetComponent<Light>() != null) continue;
                root.transform.position = Scaled(root.transform.position);
                root.transform.localScale *= factor;
            }

            foreach (var (terrain, position) in terrains)
            {
                var data = CopyTerrainData(terrain.terrainData, copyFolder, scene.name);
                data.size *= factor;
                var trees = data.treeInstances;
                for (var i = 0; i < trees.Length; i++)
                {
                    trees[i].widthScale *= factor;
                    trees[i].heightScale *= factor;
                }
                data.treeInstances = trees;
                terrain.terrainData = data;
                var collider = terrain.GetComponent<TerrainCollider>();
                if (collider != null) collider.terrainData = data;
                // Terrain ignores its transform's scale, so place it directly.
                terrain.transform.position = position;
                EditorUtility.SetDirty(data);
            }
            AssetDatabase.SaveAssets();
            EditorSceneManager.MarkSceneDirty(scene);
        }

        public static TerrainData CopyTerrainData(TerrainData original, string folder, string sceneName)
        {
            var source = AssetDatabase.GetAssetPath(original);
            var target = $"{folder}/{sceneName} terrain (XRPod copy).asset";
            if (source == target) return original; // already our copy
            AssetDatabase.DeleteAsset(target);
            AssetDatabase.CopyAsset(source, target);
            return AssetDatabase.LoadAssetAtPath<TerrainData>(target);
        }

        // Adds a mesh collider to every visible object that has none, except
        // tiny things (stepped over), water (waded into) and our own zones.
        // Returns how many got one.
        public static int AddColliders(Scene scene)
        {
            var added = 0;
            foreach (var root in scene.GetRootGameObjects())
            {
                if (IsOurs(root)) continue;
                foreach (var renderer in root.GetComponentsInChildren<MeshRenderer>(true))
                {
                    var name = renderer.name.ToLowerInvariant();
                    if (name.Contains("water") || name.Contains("ocean") || name.Contains("sea")) continue;
                    if (WalkThrough(name)) continue;
                    if (renderer.GetComponent<Collider>() != null) continue;
                    if (renderer.bounds.size.magnitude < 0.6f) continue;
                    var mesh = renderer.GetComponent<MeshFilter>();
                    if (mesh == null || mesh.sharedMesh == null) continue;
                    var collider = Undo.AddComponent<MeshCollider>(renderer.gameObject);
                    collider.sharedMesh = mesh.sharedMesh;
                    added++;
                }
            }
            EditorSceneManager.MarkSceneDirty(scene);
            return added;
        }

        // Soft plants you'd walk through in real life (and leaves overhead).
        static readonly string[] SoftWords =
            { "grass", "flower", "fern", "plant", "bush", "shrub", "weed", "leaf", "leaves", "foliage", "branch" };

        static bool WalkThrough(string name)
        {
            foreach (var word in SoftWords)
                if (name.Contains(word)) return true;
            return false;
        }
    }
}
