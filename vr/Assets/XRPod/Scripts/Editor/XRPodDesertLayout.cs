// XRPod > Desert: Pull Things Closer (within 50 m)
//
// Desert_v1 is about 440 x 500 m with its camps, rocks, tower and raft far
// apart, so there's a lot of walking between them. This moves them closer
// to the start spot, so the farthest one ends up about 50 m away and
// everything else in proportion, without deleting or resizing anything:
//   - the ground tiles, cliffs and sky stay where they are,
//   - small things (grass, pebbles) stay too, so the ground doesn't get
//     crowded,
//   - everything bigger (rocks, camps, the tower, the raft, their lights) is
//     grouped with what's near it (a camp moves as one piece, nothing inside
//     it gets squeezed), and each group slides towards the start, is set
//     back down on the ground there, and is nudged outwards if it would
//     land on another group or on the start spot.
// Ctrl + Z undoes it. The desert's shade zones are placed again afterwards
// (XRPodZoneTools).

using System.Collections.Generic;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace XRPod.VR
{
    static class XRPodDesertLayout
    {
        const float Farthest50 = 50f;    // the farthest group ends up about this far away (m)
        const float SmallSize = 1.5f;    // smaller than this (m) stays put
        const float GroupGap = 4f;       // things closer than this move together
        const float StartClearance = 5f; // nothing lands within this of the start
        const float Spacing = 1.5f;      // kept between groups after moving

        sealed class Group
        {
            public readonly List<Transform> Members = new List<Transform>();
            public Vector2 Center;
            public float Radius;
        }

        [MenuItem("XRPod/Desert: Pull Things Closer (within 50 m)")]
        static void PullCloser()
        {
            if (EditorApplication.isPlayingOrWillChangePlaymode)
            {
                EditorUtility.DisplayDialog("XRPod", "Stop Play mode first.", "OK");
                return;
            }
            if (!EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo()) return;
            var path = "Assets/XRPod/Scenes/Desert_v1.unity";
            var scene = SceneManager.GetActiveScene();
            if (scene.name != "Desert_v1") scene = EditorSceneManager.OpenScene(path, OpenSceneMode.Single);

            var spawn = Object.FindAnyObjectByType<EnvironmentSpawnPoint>();
            if (spawn == null)
            {
                EditorUtility.DisplayDialog("XRPod", "Desert_v1 has no start spot. Run XRPod > Make Desert v1 first.", "OK");
                return;
            }
            var start = new Vector2(spawn.transform.position.x, spawn.transform.position.z);

            XRPodWorldFit.AddColliders(scene); // the ground needs them to be found
            Physics.SyncTransforms();

            var ground = new HashSet<Collider>();
            var things = new List<(Transform t, Bounds b)>();
            foreach (var root in scene.GetRootGameObjects())
                Collect(root.transform, ground, things);

            var groups = MakeGroups(things);
            var before = Farthest(groups, start);

            // Old ground height under each group, before anything moves.
            var oldGround = new float[groups.Count];
            for (var g = 0; g < groups.Count; g++) oldGround[g] = GroundAt(groups[g].Center, ground);

            if (before <= Farthest50 + 1f)
            {
                EditorUtility.DisplayDialog("XRPod", $"Everything is already within {before:0} m of the start: nothing moved.", "OK");
                return;
            }

            // New places: all distances scaled so the farthest is ~50 m, then
            // pushed apart where they'd overlap.
            var pull = Farthest50 / before;
            var targets = new Vector2[groups.Count];
            for (var g = 0; g < groups.Count; g++)
                targets[g] = start + (groups[g].Center - start) * pull;
            Spread(groups, targets, start);

            var moved = new List<Object>();
            foreach (var group in groups)
            foreach (var t in group.Members)
                moved.Add(t);
            Undo.RecordObjects(moved.ToArray(), "Pull desert things closer");

            for (var g = 0; g < groups.Count; g++)
            {
                var shift = targets[g] - groups[g].Center;
                var rise = GroundAt(targets[g], ground) - oldGround[g];
                foreach (var t in groups[g].Members)
                    t.position += new Vector3(shift.x, rise, shift.y);
                groups[g].Center = targets[g];
            }
            Physics.SyncTransforms();
            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene);

            var zones = XRPodZoneTools.PlaceDesertZones();
            EditorUtility.DisplayDialog("XRPod",
                $"Moved {groups.Count} groups ({moved.Count} objects) towards the start. " +
                $"The farthest is now {Farthest(groups, start):0} m away (was {before:0} m). " +
                "Ground, cliffs, sky, grass and pebbles stayed where they were.\n\n" +
                "Ctrl + Z undoes it.\n\n" + zones, "OK");
        }

        // Sorts the scene into ground (kept, used to find the floor) and the
        // things to move: each prefab placed in the scene, or a light or
        // other object on its own, but not its parts.
        static void Collect(Transform t, HashSet<Collider> ground, List<(Transform, Bounds)> things)
        {
            var name = t.name.ToLowerInvariant();
            if (IsOurs(t) || name.Contains("cloud") || name.Contains("bird") || name.Contains("sky")
                || t.GetComponent<Light>() is Light l && l.type == LightType.Directional
                || t.GetComponent<Terrain>() != null || name.Contains("volume") || name.Contains("reflection probe"))
                return;
            // Ground tiles and cliffs ("..._Terrain_Rock_...") stay. Only the
            // tiles count as the floor, so nothing gets set down on a cliff top.
            if (name.Contains("terrain"))
            {
                if (!name.Contains("rock"))
                    foreach (var c in t.GetComponentsInChildren<Collider>(true)) ground.Add(c);
                return;
            }

            var placed = PrefabUtility.IsOutermostPrefabInstanceRoot(t.gameObject);
            var alone = t.childCount == 0 && (t.GetComponent<Renderer>() != null || t.GetComponent<Light>() != null);
            if (placed || alone)
            {
                if (TryBounds(t, out var b) && Mathf.Max(b.size.x, b.size.z) < SmallSize && t.GetComponent<Light>() == null)
                    return; // small: stays
                things.Add((t, TryBounds(t, out var bounds) ? bounds : new Bounds(t.position, Vector3.zero)));
                return;
            }
            foreach (Transform child in t) Collect(child, ground, things);
        }

        static bool IsOurs(Transform t) =>
            t.GetComponentInParent<ZoneVolume>(true) != null || t.GetComponent<EnvironmentSpawnPoint>() != null
            || t.name == "Zones" || t.name.Contains("(invisible)");

        static bool TryBounds(Transform t, out Bounds bounds)
        {
            bounds = default;
            var found = false;
            foreach (var r in t.GetComponentsInChildren<Renderer>(true))
            {
                if (!found) bounds = r.bounds;
                else bounds.Encapsulate(r.bounds);
                found = true;
            }
            return found;
        }

        // Things whose footprints come within GroupGap of each other end up
        // in one group (a camp, a rock pile).
        static List<Group> MakeGroups(List<(Transform t, Bounds b)> things)
        {
            var n = things.Count;
            var parent = new int[n];
            for (var i = 0; i < n; i++) parent[i] = i;
            int Find(int i) => parent[i] == i ? i : parent[i] = Find(parent[i]);
            for (var i = 0; i < n; i++)
            for (var j = i + 1; j < n; j++)
            {
                var a = things[i].b;
                var b = things[j].b;
                var dx = Mathf.Max(0f, Mathf.Abs(a.center.x - b.center.x) - a.extents.x - b.extents.x);
                var dz = Mathf.Max(0f, Mathf.Abs(a.center.z - b.center.z) - a.extents.z - b.extents.z);
                if (dx * dx + dz * dz <= GroupGap * GroupGap) parent[Find(i)] = Find(j);
            }

            var byRoot = new Dictionary<int, (Group group, Bounds bounds)>();
            for (var i = 0; i < n; i++)
            {
                var r = Find(i);
                if (!byRoot.TryGetValue(r, out var entry)) entry = (new Group(), things[i].b);
                else entry.bounds.Encapsulate(things[i].b);
                entry.group.Members.Add(things[i].t);
                byRoot[r] = entry;
            }
            var groups = new List<Group>();
            foreach (var (group, bounds) in byRoot.Values)
            {
                group.Center = new Vector2(bounds.center.x, bounds.center.z);
                group.Radius = Mathf.Max(bounds.extents.x, bounds.extents.z);
                groups.Add(group);
            }
            return groups;
        }

        // Pushes groups outwards (away from the start) until none overlap
        // each other or the start spot. Groups nearer the start keep their place.
        static void Spread(List<Group> groups, Vector2[] targets, Vector2 start)
        {
            var order = new List<int>();
            for (var g = 0; g < groups.Count; g++) order.Add(g);
            order.Sort((a, b) => (targets[a] - start).sqrMagnitude.CompareTo((targets[b] - start).sqrMagnitude));
            var placed = new List<int>();
            foreach (var g in order)
            {
                var away = targets[g] - start;
                var direction = away.sqrMagnitude > 0.01f ? away.normalized : Vector2.up;
                for (var tries = 0; tries < 400; tries++)
                {
                    var clash = (targets[g] - start).magnitude < groups[g].Radius + StartClearance;
                    foreach (var other in placed)
                        if ((targets[g] - targets[other]).magnitude < groups[g].Radius + groups[other].Radius + Spacing)
                            clash = true;
                    if (!clash) break;
                    targets[g] += direction * 0.5f;
                }
                placed.Add(g);
            }
        }

        // Height of the desert floor (its ground tiles) at a spot.
        static float GroundAt(Vector2 spot, HashSet<Collider> ground)
        {
            var best = float.MinValue;
            foreach (var hit in Physics.RaycastAll(new Vector3(spot.x, 1000f, spot.y), Vector3.down, 2000f, ~0, QueryTriggerInteraction.Ignore))
                if (ground.Contains(hit.collider) && hit.point.y > best) best = hit.point.y;
            return best == float.MinValue ? 0f : best;
        }

        static float Farthest(List<Group> groups, Vector2 start)
        {
            var far = 0f;
            foreach (var g in groups) far = Mathf.Max(far, (g.Center - start).magnitude);
            return far;
        }
    }
}
