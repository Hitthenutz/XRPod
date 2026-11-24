// Puts the Forest and Desert zones where the scenery's shade really is
// (vr/docs/ZONES.md):
//
//   XRPod > Forest: Place Zones From Real Shade   (run with Forest_v1)
//   XRPod > Desert: Place Zones From Real Shade   (run with Desert_v1)
//
// (Make Forest v1 runs the forest one by itself.)
//
// Both check every square metre within 60 m of the start: whether you can
// walk there (not inside a rock, room for your head, no climbing), and
// whether a line from your body towards the scene's sun is blocked. Then:
//
//   Forest                             Desert
//   forest-shade    under the trees    desert-shade     in a shadow
//   forest-clearing open sky, 7 m+     desert-covered   under a roof or awning
//                   from any tree      desert-ridge     highest open ground
//   forest-hilltop  highest open       desert-campfire  next to a fire pit
//                   ground
//   forest-open     everywhere else    desert-open      everywhere else
//
// Trees painted on a terrain have no solid leaves, so for the forest the
// tool briefly adds a copy of each nearby tree's real leaf and trunk meshes
// to block the sun, and removes them again (nothing is saved). A shadow is
// made of boxes that follow its shape. A picture of the result is saved to
// vr/Logs/xrpod-<world>-zones.png. Run again any time, e.g. after moving the
// sun; it replaces the scene's old zones.

using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using XRPod.VR.Core;

namespace XRPod.VR
{
    static class XRPodZoneTools
    {
        const string SceneFolder = "Assets/XRPod/Scenes";

        const float Cell = 1f;          // metres per grid square
        const float Reach = 60f;        // checked this far from the start
        const float Headroom = 1.9f;    // a person fits under anything higher
        const float MaxStep = 0.6f;     // between neighbouring squares, or it's a climb
        const int MinShadeCells = 3;    // smaller shadows (a pole) are skipped
        const int MinRidgeCells = 6;
        const int MinClearingCells = 20;
        const int TreeLayer = 31;       // the temporary tree copies; ignored when finding the ground

        enum Spot : byte { Unreachable, Sun, Shade, Covered, Ridge, Fire, Clearing }

        // What one world calls its zones. null: that kind isn't used there.
        sealed class World
        {
            public string Name;              // also the scene name without _v1
            public EnvironmentId Environment;
            public int MenuKey;              // the Play-mode key that shows it
            public string Open, Shade, Covered, Ridge, Clearing, Campfire;
            public bool TreeShade;           // add the terrain's trees as sun blockers
            public float ClearingDistance;   // open sky this far from any tree trunk
        }

        static readonly World Forest = new World
        {
            Name = "Forest", Environment = EnvironmentId.Forest, MenuKey = 2,
            Open = "forest-open", Shade = "forest-shade", Ridge = "forest-hilltop", Clearing = "forest-clearing",
            TreeShade = true, ClearingDistance = 7f,
        };

        static readonly World Desert = new World
        {
            Name = "Desert", Environment = EnvironmentId.Desert, MenuKey = 3,
            Open = "desert-open", Shade = "desert-shade", Covered = "desert-covered", Ridge = "desert-ridge",
            Campfire = "desert-campfire",
        };

        [MenuItem("XRPod/Forest: Place Zones From Real Shade")]
        static void ForestMenu()
        {
            if (!ReadyToEdit()) return;
            var message = PlaceZones(Forest);
            if (message != null) Dialog(message);
        }

        [MenuItem("XRPod/Desert: Place Zones From Real Shade")]
        static void DesertMenu()
        {
            if (!ReadyToEdit()) return;
            var message = PlaceZones(Desert);
            if (message != null) Dialog(message);
        }

        // For XRPod > Make Forest v1, which has just made and opened Forest_v1.
        internal static string PlaceForestZones() => PlaceZones(Forest) ?? "The zones weren't placed (see the message before).";

        // For XRPod > Desert: Pull Things Closer, after moving things.
        internal static string PlaceDesertZones() => PlaceZones(Desert) ?? "The zones weren't placed (see the message before).";

        // Returns a summary for the user, or null if it stopped (after
        // telling them why).
        static string PlaceZones(World world)
        {
            var sceneName = world.Name + "_v1";
            var path = $"{SceneFolder}/{sceneName}.unity";
            var scene = SceneManager.GetActiveScene();
            if (scene.name != sceneName)
            {
                if (!File.Exists(path))
                {
                    Dialog($"{sceneName} is missing. Run XRPod > Make {world.Name} v1 first.");
                    return null;
                }
                scene = EditorSceneManager.OpenScene(path, OpenSceneMode.Single);
            }

            var spawn = Find<EnvironmentSpawnPoint>(scene);
            var sun = SunLight(scene);
            if (spawn == null || sun == null)
            {
                Dialog($"Missing in {sceneName}: {(spawn == null ? "the start spot " : "")}{(sun == null ? "a sun (directional light)" : "")}.");
                return null;
            }
            var toSun = -sun.transform.forward;
            if (toSun.y < 0.05f)
            {
                Dialog("The sun is at or below the horizon, so there are no proper shadows. " +
                       "Raise the sun (its X rotation) and run this again.");
                return null;
            }

            // Old zones go first so nothing is left from the test world.
            var zones = FreshZonesRoot(scene);
            var added = XRPodWorldFit.AddColliders(scene);

            var start = spawn.transform.position;
            var n = Mathf.RoundToInt(2f * Reach / Cell);
            var origin = new Vector2(start.x - Reach, start.z - Reach);
            var ground = new float[n, n];
            var overhead = new bool[n, n];
            var standable = new bool[n, n];
            var spots = new Spot[n, n];
            var trunks = new List<Vector2>();
            bool[,] reach;

            GameObject treeCopies = null;
            var backfaces = Physics.queriesHitBackfaces;
            try
            {
                if (world.TreeShade) treeCopies = AddTreeCopies(scene, start, trunks);
                Physics.SyncTransforms();

                for (var i = 0; i < n; i++)
                for (var j = 0; j < n; j++)
                {
                    var x = origin.x + (i + 0.5f) * Cell;
                    var z = origin.y + (j + 0.5f) * Cell;
                    standable[i, j] = FindGround(new Vector3(x, start.y, z), out ground[i, j], out overhead[i, j]);
                }

                // Where you can actually walk to from the start, without climbing.
                reach = Reachable(standable, ground, CellOf(start, origin, n), n);

                // Sun or shade at each walkable square: shaded if at least two
                // of feet, chest and head can't see the sun.
                Physics.queriesHitBackfaces = false;
                for (var i = 0; i < n; i++)
                for (var j = 0; j < n; j++)
                {
                    if (!reach[i, j]) continue;
                    var p = new Vector3(origin.x + (i + 0.5f) * Cell, ground[i, j], origin.y + (j + 0.5f) * Cell);
                    var blocked = 0;
                    foreach (var h in new[] { 0.5f, 1.1f, 1.7f })
                        if (CastSolid(p + Vector3.up * h, toSun, 300f, ~0, out _)) blocked++;
                    spots[i, j] = blocked < 2 ? Spot.Sun
                        : overhead[i, j] && world.Covered != null ? Spot.Covered : Spot.Shade;
                }
            }
            finally
            {
                Physics.queriesHitBackfaces = backfaces;
                if (treeCopies != null) Object.DestroyImmediate(treeCopies);
                Physics.SyncTransforms();
            }

            // The ridge or hilltop: the highest tenth of the open ground, if
            // it's at least 2 m above the start (otherwise there isn't one).
            var heights = new List<float>();
            for (var i = 0; i < n; i++)
            for (var j = 0; j < n; j++)
                if (spots[i, j] == Spot.Sun) heights.Add(ground[i, j]);
            if (world.Ridge != null && heights.Count > 0)
            {
                heights.Sort();
                var cut = Mathf.Max(heights[(int)(heights.Count * 0.9f)], start.y + 2f);
                for (var i = 0; i < n; i++)
                for (var j = 0; j < n; j++)
                    if (spots[i, j] == Spot.Sun && ground[i, j] >= cut) spots[i, j] = Spot.Ridge;
            }

            // Clearings: open sky well away from every tree.
            if (world.Clearing != null)
            {
                var far = world.ClearingDistance * world.ClearingDistance;
                for (var i = 0; i < n; i++)
                for (var j = 0; j < n; j++)
                {
                    if (spots[i, j] != Spot.Sun) continue;
                    var p = new Vector2(origin.x + (i + 0.5f) * Cell, origin.y + (j + 0.5f) * Cell);
                    if (trunks.TrueForAll(t => (t - p).sqrMagnitude > far)) spots[i, j] = Spot.Clearing;
                }
            }

            DropSmall(spots, Spot.Shade, MinShadeCells, n);
            DropSmall(spots, Spot.Covered, MinShadeCells, n);
            DropSmall(spots, Spot.Ridge, MinRidgeCells, n);
            DropSmall(spots, Spot.Clearing, MinClearingCells, n);

            var env = world.Environment;
            var groundRange = MinMax(ground, reach, n);
            AddBox(zones, world.Open, world.Shade == null ? ZoneType.Neutral : ZoneTypeOfOpen(world), env, 0,
                new Vector2(start.x, start.z), new Vector2(400f, 400f), groundRange.x - 20f, groundRange.y + 20f);

            var lines = new List<string>();
            void Kind(string id, Spot kind, ZoneType type, int priority, string what)
            {
                if (id == null) return;
                var boxes = AddRectangles(zones, spots, kind, ground, origin, n, id, type, env, priority);
                lines.Add($"{what}: {Count(spots, kind, n)} m² ({boxes} boxes)");
            }
            Kind(world.Shade, Spot.Shade, ZoneType.Cool, 15, world.TreeShade ? "Shade under the trees" : "Shade");
            Kind(world.Covered, Spot.Covered, ZoneType.Cool, 20, "Under a roof or awning");
            Kind(world.Ridge, Spot.Ridge, ZoneType.Windy, 10, "Highest open ground");
            Kind(world.Clearing, Spot.Clearing, ZoneType.Hot, 10, "Sunny clearings");
            if (world.Campfire != null)
                lines.Add($"Campfires: {AddCampfires(scene, zones, spots, ground, origin, n, world.Campfire, env)}");

            var map = SaveMap(spots, CellOf(start, origin, n), n, world.Name.ToLowerInvariant());
            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene);

            return $"{world.Name} zones placed from the sun's real shadows, within {Reach:0} m of the start" +
                   (world.TreeShade ? $" ({trunks.Count} trees checked)" : "") + ".\n\n" +
                   string.Join("\n", lines) + "\n" +
                   (added > 0 ? $"Added collision shapes to {added} object(s) first.\n" : "") +
                   $"\nSaved. A map of it is in vr/Logs/{map}. Open Bootstrap, press Play and {world.MenuKey}, " +
                   "then Z to see the zone pads.";
        }

        // The base zone's rough hint: the desert's open sun is hot, the
        // forest floor between the trees mild.
        static ZoneType ZoneTypeOfOpen(World world) => world.Environment == EnvironmentId.Desert ? ZoneType.Hot : ZoneType.Neutral;

        // ------------------------------------------------------ tree shade

        // Copies of the terrain's painted trees near the start, with their
        // real meshes as colliders (leaves and trunk), so the sun test sees
        // their shade. Hidden, never saved; the caller destroys the root.
        // Adds each tree's trunk position to `trunks`.
        static GameObject AddTreeCopies(Scene scene, Vector3 start, List<Vector2> trunks)
        {
            var root = new GameObject("XRPod tree shade (temporary)") { hideFlags = HideFlags.HideAndDontSave };
            var near = Reach + 20f; // a tree just outside can still shade the edge
            foreach (var sceneRoot in scene.GetRootGameObjects())
            foreach (var terrain in sceneRoot.GetComponentsInChildren<Terrain>(true))
            {
                var data = terrain.terrainData;
                if (data == null) continue;
                var prototypes = data.treePrototypes;
                foreach (var tree in data.treeInstances)
                {
                    var position = Vector3.Scale(tree.position, data.size) + terrain.transform.position;
                    if (new Vector2(position.x - start.x, position.z - start.z).sqrMagnitude > near * near) continue;
                    if (tree.prototypeIndex < 0 || tree.prototypeIndex >= prototypes.Length) continue;
                    var prefab = prototypes[tree.prototypeIndex].prefab;
                    if (prefab == null) continue;
                    trunks.Add(new Vector2(position.x, position.z));

                    var copy = new GameObject(prefab.name) { hideFlags = HideFlags.HideAndDontSave, layer = TreeLayer };
                    copy.transform.SetParent(root.transform, false);
                    copy.transform.SetPositionAndRotation(position, Quaternion.Euler(0f, tree.rotation * Mathf.Rad2Deg, 0f));
                    copy.transform.localScale = new Vector3(tree.widthScale, tree.heightScale, tree.widthScale);
                    foreach (var (mesh, local) in DetailedMeshes(prefab))
                    {
                        var part = new GameObject("part") { hideFlags = HideFlags.HideAndDontSave, layer = TreeLayer };
                        part.transform.SetParent(copy.transform, false);
                        part.transform.localPosition = local.GetColumn(3);
                        part.transform.localRotation = local.rotation;
                        part.transform.localScale = local.lossyScale;
                        part.AddComponent<MeshCollider>().sharedMesh = mesh;
                    }
                }
            }
            return root;
        }

        // The meshes of a tree's most detailed look (its first LOD if it has
        // levels), each with its placement relative to the tree's root.
        static List<(Mesh mesh, Matrix4x4 local)> DetailedMeshes(GameObject prefab)
        {
            var found = new List<(Mesh, Matrix4x4)>();
            var toRoot = prefab.transform.worldToLocalMatrix;
            var renderers = new List<Renderer>();
            var lods = prefab.GetComponentInChildren<LODGroup>(true);
            if (lods != null && lods.lodCount > 0) renderers.AddRange(lods.GetLODs()[0].renderers);
            else renderers.AddRange(prefab.GetComponentsInChildren<MeshRenderer>(true));
            foreach (var renderer in renderers)
            {
                if (renderer == null || !renderer.TryGetComponent<MeshFilter>(out var filter) || filter.sharedMesh == null) continue;
                found.Add((filter.sharedMesh, toRoot * renderer.transform.localToWorldMatrix));
            }
            return found;
        }

        // ------------------------------------------------------ the grid

        // The floor under (x, z): the lowest surface you could stand on,
        // i.e. not inside a rock and with room for a person above it.
        // overhead: something (a roof, an awning) is above, within 6 m.
        // Leaves (the temporary tree copies) don't count: you'd walk under
        // or through them.
        static bool FindGround(Vector3 column, out float y, out bool overhead)
        {
            y = 0f;
            overhead = false;
            var solid = ~(1 << TreeLayer);
            Physics.queriesHitBackfaces = false;
            var hits = new List<RaycastHit>();
            foreach (var hit in Physics.RaycastAll(column + Vector3.up * 150f, Vector3.down, 400f, solid, QueryTriggerInteraction.Ignore))
                if (!Ignored(hit.collider)) hits.Add(hit);
            if (hits.Count == 0) return false;
            hits.Sort((a, b) => a.point.y.CompareTo(b.point.y));

            // Looking up from inside a rock you see the inside of its surface
            // (its normal faces the same way as the ray).
            Physics.queriesHitBackfaces = true;
            foreach (var hit in hits)
            {
                var from = hit.point + Vector3.up * 0.05f;
                if (!CastSolid(from, Vector3.up, 60f, solid, out var above))
                {
                    y = hit.point.y;
                    return true;
                }
                if (Vector3.Dot(above.normal, Vector3.up) > 0f) continue; // inside something
                if (above.distance < Headroom) continue;                  // too low to stand
                y = hit.point.y;
                overhead = above.distance < 6f;
                return true;
            }
            return false;
        }

        // The nearest hit on something solid that casts a real shadow.
        // Skipped: the sky's cloud rings and birds, and anything the renderer
        // draws without a shadow (it couldn't shade you in the game either).
        static bool CastSolid(Vector3 from, Vector3 direction, float distance, int layers, out RaycastHit nearest)
        {
            nearest = default;
            var found = false;
            foreach (var hit in Physics.RaycastAll(from, direction, distance, layers, QueryTriggerInteraction.Ignore))
            {
                if (Ignored(hit.collider) || (found && hit.distance >= nearest.distance)) continue;
                nearest = hit;
                found = true;
            }
            return found;
        }

        static bool Ignored(Collider collider)
        {
            var name = collider.name.ToLowerInvariant();
            if (name.Contains("cloud") || name.Contains("sky") || name.Contains("bird")) return true;
            return collider.TryGetComponent<Renderer>(out var look)
                   && look.shadowCastingMode == UnityEngine.Rendering.ShadowCastingMode.Off;
        }

        // Flood fill from the start over standable squares, stepping at most
        // MaxStep up or down between neighbours.
        static bool[,] Reachable(bool[,] standable, float[,] ground, Vector2Int start, int n)
        {
            var reach = new bool[n, n];
            // The start square itself, or the nearest standable one.
            if (!standable[start.x, start.y])
            {
                var best = float.MaxValue;
                for (var i = 0; i < n; i++)
                for (var j = 0; j < n; j++)
                {
                    var d = (new Vector2Int(i, j) - start).sqrMagnitude;
                    if (standable[i, j] && d < best)
                    {
                        best = d;
                        start = new Vector2Int(i, j);
                    }
                }
                if (best == float.MaxValue) return reach;
            }
            var queue = new Queue<Vector2Int>();
            queue.Enqueue(start);
            reach[start.x, start.y] = true;
            var steps = new[] { Vector2Int.up, Vector2Int.down, Vector2Int.left, Vector2Int.right };
            while (queue.Count > 0)
            {
                var c = queue.Dequeue();
                foreach (var s in steps)
                {
                    var m = c + s;
                    if (m.x < 0 || m.y < 0 || m.x >= n || m.y >= n || reach[m.x, m.y] || !standable[m.x, m.y]) continue;
                    if (Mathf.Abs(ground[m.x, m.y] - ground[c.x, c.y]) > MaxStep) continue;
                    reach[m.x, m.y] = true;
                    queue.Enqueue(m);
                }
            }
            return reach;
        }

        // Turns patches smaller than `min` squares back into open sun.
        static void DropSmall(Spot[,] spots, Spot kind, int min, int n)
        {
            var seen = new bool[n, n];
            var steps = new[] { Vector2Int.up, Vector2Int.down, Vector2Int.left, Vector2Int.right };
            for (var i = 0; i < n; i++)
            for (var j = 0; j < n; j++)
            {
                if (seen[i, j] || spots[i, j] != kind) continue;
                var patch = new List<Vector2Int>();
                var queue = new Queue<Vector2Int>();
                queue.Enqueue(new Vector2Int(i, j));
                seen[i, j] = true;
                while (queue.Count > 0)
                {
                    var c = queue.Dequeue();
                    patch.Add(c);
                    foreach (var s in steps)
                    {
                        var m = c + s;
                        if (m.x < 0 || m.y < 0 || m.x >= n || m.y >= n || seen[m.x, m.y] || spots[m.x, m.y] != kind) continue;
                        seen[m.x, m.y] = true;
                        queue.Enqueue(m);
                    }
                }
                if (patch.Count < min)
                    foreach (var c in patch) spots[c.x, c.y] = Spot.Sun;
            }
        }

        // Covers every square of `kind` with as few rectangles as it can
        // (grow right, then down), one zone box each, all with the same id.
        static int AddRectangles(Transform zones, Spot[,] spots, Spot kind, float[,] ground, Vector2 origin, int n,
            string id, ZoneType type, EnvironmentId environment, int priority)
        {
            var used = new bool[n, n];
            var group = new GameObject(id).transform;
            group.SetParent(zones, false);
            var boxes = 0;
            for (var j = 0; j < n; j++)
            for (var i = 0; i < n; i++)
            {
                if (used[i, j] || spots[i, j] != kind) continue;
                var i1 = i;
                while (i1 + 1 < n && !used[i1 + 1, j] && spots[i1 + 1, j] == kind) i1++;
                var j1 = j;
                while (j1 + 1 < n && RowFree(spots, used, kind, i, i1, j1 + 1)) j1++;

                var low = float.MaxValue;
                var high = float.MinValue;
                for (var a = i; a <= i1; a++)
                for (var b = j; b <= j1; b++)
                {
                    used[a, b] = true;
                    low = Mathf.Min(low, ground[a, b]);
                    high = Mathf.Max(high, ground[a, b]);
                }
                var center = new Vector2(origin.x + (i + i1 + 1) * 0.5f * Cell, origin.y + (j + j1 + 1) * 0.5f * Cell);
                var size = new Vector2((i1 - i + 1) * Cell, (j1 - j + 1) * Cell);
                AddBox(group, id, type, environment, priority, center, size, low, high);
                boxes++;
            }
            if (boxes == 0) Object.DestroyImmediate(group.gameObject);
            return boxes;
        }

        static bool RowFree(Spot[,] spots, bool[,] used, Spot kind, int i0, int i1, int j)
        {
            for (var i = i0; i <= i1; i++)
                if (used[i, j] || spots[i, j] != kind) return false;
            return true;
        }

        // A warm zone 3.5 m across around each fire pit you can walk up to.
        static int AddCampfires(Scene scene, Transform zones, Spot[,] spots, float[,] ground, Vector2 origin, int n,
            string id, EnvironmentId environment)
        {
            var placed = new List<Vector3>();
            foreach (var root in scene.GetRootGameObjects())
            foreach (var renderer in root.GetComponentsInChildren<Renderer>(true))
            {
                var name = renderer.name.ToLowerInvariant();
                if (!(name.Contains("fireplace") || name.Contains("campfire") || name.Contains("fire_pit"))) continue;
                var c = renderer.bounds.center;
                if (placed.Exists(p => Vector3.Distance(p, c) < 2f)) continue;
                var cell = CellOf(c, origin, n);
                if (spots[cell.x, cell.y] == Spot.Unreachable && !NearReachable(spots, cell, 2, n)) continue;
                placed.Add(c);
                var floor = spots[cell.x, cell.y] == Spot.Unreachable ? c.y - renderer.bounds.extents.y : ground[cell.x, cell.y];
                AddBox(zones, id, ZoneType.Hot, environment, 25, new Vector2(c.x, c.z), new Vector2(3.5f, 3.5f), floor, floor);
                for (var a = -1; a <= 1; a++)
                for (var b = -1; b <= 1; b++)
                {
                    var x = cell.x + a;
                    var y = cell.y + b;
                    if (x >= 0 && y >= 0 && x < n && y < n && spots[x, y] != Spot.Unreachable) spots[x, y] = Spot.Fire;
                }
            }
            return placed.Count;
        }

        static bool NearReachable(Spot[,] spots, Vector2Int cell, int radius, int n)
        {
            for (var a = -radius; a <= radius; a++)
            for (var b = -radius; b <= radius; b++)
            {
                var x = cell.x + a;
                var y = cell.y + b;
                if (x >= 0 && y >= 0 && x < n && y < n && spots[x, y] != Spot.Unreachable) return true;
            }
            return false;
        }

        // A top-down picture: sand = sun, light blue = shade, dark blue =
        // under a roof, orange = ridge or hilltop, yellow = clearing, red =
        // fire, grey = can't walk there, white = the start. +z (the way you
        // face at the start) is up. Returns the file name.
        static string SaveMap(Spot[,] spots, Vector2Int start, int n, string world)
        {
            const int scale = 6;
            var image = new Texture2D(n * scale, n * scale, TextureFormat.RGB24, false);
            var colors = new Dictionary<Spot, Color>
            {
                [Spot.Unreachable] = new Color(0.25f, 0.25f, 0.25f),
                [Spot.Sun] = new Color(0.93f, 0.8f, 0.55f),
                [Spot.Shade] = new Color(0.35f, 0.55f, 0.9f),
                [Spot.Covered] = new Color(0.12f, 0.22f, 0.6f),
                [Spot.Ridge] = new Color(0.95f, 0.55f, 0.15f),
                [Spot.Fire] = new Color(0.9f, 0.15f, 0.1f),
                [Spot.Clearing] = new Color(1f, 0.95f, 0.3f),
            };
            for (var i = 0; i < n; i++)
            for (var j = 0; j < n; j++)
            {
                var color = new Vector2Int(i, j) == start ? Color.white : colors[spots[i, j]];
                // Grid lines every 10 m.
                for (var a = 0; a < scale; a++)
                for (var b = 0; b < scale; b++)
                {
                    var line = (i % 10 == 0 && a == 0) || (j % 10 == 0 && b == 0);
                    image.SetPixel(i * scale + a, j * scale + b, line ? color * 0.8f : color);
                }
            }
            image.Apply();
            var folder = Path.Combine(Application.dataPath, "..", "Logs");
            Directory.CreateDirectory(folder);
            var file = $"xrpod-{world}-zones.png";
            File.WriteAllBytes(Path.Combine(folder, file), image.EncodeToPNG());
            Object.DestroyImmediate(image);
            return file;
        }

        // ------------------------------------------------------------ shared

        static bool ReadyToEdit()
        {
            if (EditorApplication.isPlayingOrWillChangePlaymode)
            {
                Dialog("Stop Play mode first.");
                return false;
            }
            return EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo();
        }

        // Removes every zone in the scene and returns a new, empty "Zones".
        static Transform FreshZonesRoot(Scene scene)
        {
            foreach (var root in scene.GetRootGameObjects())
                if (root.name == "Zones") Object.DestroyImmediate(root);
            foreach (var root in scene.GetRootGameObjects())
            foreach (var zone in root.GetComponentsInChildren<ZoneVolume>(true))
                if (zone != null) Object.DestroyImmediate(zone.gameObject);
            var zones = new GameObject("Zones");
            SceneManager.MoveGameObjectToScene(zones, scene);
            return zones.transform;
        }

        // One zone box: `size` metres across on the ground, from 1 m below
        // the lowest ground under it (`low`) to 4 m above the highest (`high`),
        // so the probe at head height is inside it on slopes too. Its pad
        // (shown with Z in Play mode) lies on the lowest ground.
        static void AddBox(Transform parent, string id, ZoneType type, EnvironmentId environment, int priority,
            Vector2 center, Vector2 size, float low, float high)
        {
            var zone = new GameObject(id);
            zone.transform.SetParent(parent, false);
            zone.transform.position = new Vector3(center.x, low, center.y);

            var box = zone.AddComponent<BoxCollider>();
            box.isTrigger = true;
            var height = high - low + 5f;
            box.center = new Vector3(0f, height / 2f - 1f, 0f);
            box.size = new Vector3(size.x, height, size.y);

            var volume = new SerializedObject(zone.AddComponent<ZoneVolume>());
            volume.FindProperty("zoneId").stringValue = id;
            volume.FindProperty("zoneType").intValue = (int)type;
            volume.FindProperty("environment").intValue = (int)environment;
            volume.FindProperty("priority").intValue = priority;
            volume.ApplyModifiedPropertiesWithoutUndo();

            if (priority == 0) return; // the base zone covers everything: no pad
            var pad = GameObject.CreatePrimitive(PrimitiveType.Cube);
            pad.name = "Marker";
            Object.DestroyImmediate(pad.GetComponent<Collider>());
            pad.transform.SetParent(zone.transform, false);
            pad.transform.localPosition = new Vector3(0f, 0.03f + priority * 0.002f, 0f);
            pad.transform.localScale = new Vector3(size.x, 0.02f, size.y);
            var material = AssetDatabase.LoadAssetAtPath<Material>(PadMaterial(type, priority));
            if (material != null) pad.GetComponent<Renderer>().sharedMaterial = material;
        }

        static string PadMaterial(ZoneType type, int priority)
        {
            var name = type == ZoneType.Hot ? "Zone hot 10"
                : type == ZoneType.Windy ? "Zone windy 10"
                : priority >= 20 ? "Zone cool 20" : "Zone cool 10";
            return $"Assets/XRPod/Materials/{name}.mat";
        }

        static Vector2Int CellOf(Vector3 p, Vector2 origin, int n) => new Vector2Int(
            Mathf.Clamp(Mathf.FloorToInt((p.x - origin.x) / Cell), 0, n - 1),
            Mathf.Clamp(Mathf.FloorToInt((p.z - origin.y) / Cell), 0, n - 1));

        static Vector2 MinMax(float[,] ground, bool[,] reach, int n)
        {
            var low = float.MaxValue;
            var high = float.MinValue;
            for (var i = 0; i < n; i++)
            for (var j = 0; j < n; j++)
            {
                if (!reach[i, j]) continue;
                low = Mathf.Min(low, ground[i, j]);
                high = Mathf.Max(high, ground[i, j]);
            }
            return low == float.MaxValue ? Vector2.zero : new Vector2(low, high);
        }

        static int Count(Spot[,] spots, Spot kind, int n)
        {
            var count = 0;
            for (var i = 0; i < n; i++)
            for (var j = 0; j < n; j++)
                if (spots[i, j] == kind) count++;
            return count;
        }

        // The scene's sun: its brightest directional light.
        static Light SunLight(Scene scene)
        {
            Light best = null;
            foreach (var root in scene.GetRootGameObjects())
            foreach (var light in root.GetComponentsInChildren<Light>(true))
                if (light.type == LightType.Directional && light.enabled && (best == null || light.intensity > best.intensity))
                    best = light;
            return best != null ? best : RenderSettings.sun;
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

        static void Dialog(string message) => EditorUtility.DisplayDialog("XRPod", message, "OK");
    }
}
