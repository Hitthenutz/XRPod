// One click builds placeholder scenes for testing: menu XRPod > Create Test
// Scenes. It makes, in Assets/XRPod/Scenes:
//
//   Bootstrap               the VR session and a desktop test player (camera
//                           at head height with the zone probe); never
//                           unloaded. If it already exists it's kept and only
//                           updated (start in the waiting room, sponsor
//                           available, missing scene names filled in), so
//                           things added by hand, like the Http Pod Link, stay.
//   WaitingRoom             shown when no world is picked ("none")
//   Beach, Forest, Desert   coloured ground, a sky, simple shapes and the
//                           zones from vr/docs/ZONES.md. A coloured pad shows
//                           each zone on the ground by its hint (red = hot,
//                           blue = cool, white = windy); inner rings are darker.
//                           Each world's base zone covers all of it and has
//                           no pad.
//   SponsorComingSoon       shown for "sponsor" until the sponsor's scene is in
//
// and sets the Build Profile's scene list to those scenes. Keep the zone ids
// here and in ZONES.md the same: the Pi's recipes use them.
//
// The worlds are stand-ins for testing switching and zones. Replace the
// shapes with real art later and keep (or move) the zone objects. Running it
// again replaces every scene except Bootstrap, after asking.

using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.UI;
using XRPod.VR.Core;

namespace XRPod.VR
{
    static class XRPodSceneBuilder
    {
        const string SceneFolder = "Assets/XRPod/Scenes";
        const string MaterialFolder = "Assets/XRPod/Materials";
        // Bootstrap first: it's the scene the app starts with.
        static readonly string[] SceneNames = { "Bootstrap", "WaitingRoom", "Beach", "Forest", "Desert", "SponsorComingSoon" };

        // Positions are in metres on the ground; the player starts at (0, 0)
        // facing +z, inside only the world's base zone. Rings are zones
        // inside zones with a higher priority, e.g. shore then waterline.
        readonly struct Zone
        {
            public readonly string Id;
            public readonly ZoneType Type;
            public readonly Vector2 Center;
            public readonly Vector2 Size;
            public readonly int Priority;

            public Zone(string id, ZoneType type, float x, float z, float width, float depth, int priority)
            {
                Id = id;
                Type = type;
                Center = new Vector2(x, z);
                Size = new Vector2(width, depth);
                Priority = priority;
            }

            // The whole 100 x 100 m world, lowest priority: what it feels
            // like anywhere outside the other zones.
            public static Zone Base(string id, ZoneType type) => new Zone(id, type, 0f, 0f, 100f, 100f, 0);

            public bool IsBase => Priority == 0;
        }

        [MenuItem("XRPod/Create Test Scenes")]
        static void CreateTestScenes()
        {
            if (EditorApplication.isPlayingOrWillChangePlaymode)
            {
                EditorUtility.DisplayDialog("XRPod", "Stop Play mode first.", "OK");
                return;
            }

            var existing = new List<string>();
            foreach (var name in SceneNames)
                if (name != "Bootstrap" && File.Exists(ScenePath(name))) existing.Add(name);
            if (existing.Count > 0 && !EditorUtility.DisplayDialog("XRPod",
                    "These scenes already exist and will be replaced, losing any changes made to them:\n\n" +
                    string.Join(", ", existing) + "\n\nBootstrap is kept and only updated.", "Replace", "Cancel"))
                return;
            if (!EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo()) return;

            Directory.CreateDirectory(SceneFolder);
            Directory.CreateDirectory(MaterialFolder);
            AssetDatabase.Refresh();

            if (!File.Exists(ScenePath("Bootstrap"))) BuildBootstrap();
            UpdateBootstrap();
            BuildWaitingRoom();
            BuildBeach();
            BuildForest();
            BuildDesert();
            BuildSponsorComingSoon();
            AssetDatabase.SaveAssets();

            var buildScenes = new List<EditorBuildSettingsScene>();
            foreach (var name in SceneNames)
                buildScenes.Add(new EditorBuildSettingsScene(ScenePath(name), true));
            EditorBuildSettings.scenes = buildScenes.ToArray();

            EditorSceneManager.OpenScene(ScenePath("Bootstrap"));
            Debug.Log("[XRPod] Test scenes created. Open Bootstrap and press Play.");
            EditorUtility.DisplayDialog("XRPod",
                "Test scenes are ready and Bootstrap is open. Press Play: you start in the waiting room. Then:\n\n" +
                "1 / 2 / 3   switch to Beach / Forest / Desert\n" +
                "4   sponsor (coming soon)      0   back to the waiting room\n" +
                "W A S D   walk (Shift: faster)\n" +
                "Hold right mouse   look around\n\n" +
                "Walk onto a coloured pad to enter a zone: red = hot, blue = cool, white = windy.",
                "OK");
        }

        // ------------------------------------------------------------ scenes

        static void BuildBootstrap()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            var system = new GameObject("XRPod");
            system.AddComponent<VrSystemRoot>();
            system.AddComponent<EnvironmentSceneLoader>();
            system.AddComponent<EditorTestControls>();

            // Stand-in for the XR Origin until the XR packages are set up: a
            // camera at head height that the keyboard and mouse can move.
            var player = new GameObject("Player (desktop test rig)");
            var mover = player.AddComponent<DesktopTestMover>();

            var head = new GameObject("Main Camera") { tag = "MainCamera" };
            head.transform.SetParent(player.transform, false);
            head.transform.localPosition = new Vector3(0f, 1.6f, 0f);
            head.AddComponent<Camera>().nearClipPlane = 0.05f;
            head.AddComponent<AudioListener>();

            var probe = new GameObject("ZoneProbe");
            probe.transform.SetParent(head.transform, false);
            probe.AddComponent<PlayerZoneProbe>(); // also adds its collider and Rigidbody
            var sphere = probe.GetComponent<SphereCollider>();
            sphere.isTrigger = true;
            sphere.radius = 0.15f;
            var body = probe.GetComponent<Rigidbody>();
            body.isKinematic = true;
            body.useGravity = false;

            var settings = new SerializedObject(mover);
            settings.FindProperty("head").objectReferenceValue = head.transform;
            settings.ApplyModifiedPropertiesWithoutUndo();

            Save(scene, "Bootstrap");
        }

        // Brings Bootstrap up to date without replacing it: start in the
        // waiting room, sponsor available (its "coming soon" scene), and a
        // scene name for every environment that has none yet. Names already
        // set, e.g. the sponsor's real scene, are kept.
        static void UpdateBootstrap()
        {
            var scene = EditorSceneManager.OpenScene(ScenePath("Bootstrap"), OpenSceneMode.Single);
            foreach (var root in scene.GetRootGameObjects())
            {
                var system = root.GetComponentInChildren<VrSystemRoot>();
                if (system != null)
                {
                    var settings = new SerializedObject(system);
                    settings.FindProperty("startEnvironment").intValue = (int)EnvironmentId.None;
                    settings.FindProperty("sponsorAvailable").boolValue = true;
                    settings.ApplyModifiedPropertiesWithoutUndo();
                }

                var loader = root.GetComponentInChildren<EnvironmentSceneLoader>();
                if (loader != null)
                {
                    var settings = new SerializedObject(loader);
                    var list = settings.FindProperty("scenes");
                    foreach (var wanted in EnvironmentSceneLoader.DefaultScenes())
                    {
                        SerializedProperty entry = null;
                        for (var i = 0; i < list.arraySize; i++)
                        {
                            var item = list.GetArrayElementAtIndex(i);
                            if (item.FindPropertyRelative("environment").intValue == (int)wanted.environment) entry = item;
                        }
                        if (entry == null)
                        {
                            list.arraySize++;
                            entry = list.GetArrayElementAtIndex(list.arraySize - 1);
                            entry.FindPropertyRelative("environment").intValue = (int)wanted.environment;
                            entry.FindPropertyRelative("sceneName").stringValue = "";
                        }
                        var sceneName = entry.FindPropertyRelative("sceneName");
                        if (string.IsNullOrEmpty(sceneName.stringValue)) sceneName.stringValue = wanted.sceneName;
                    }
                    settings.ApplyModifiedPropertiesWithoutUndo();
                }
            }
            EditorSceneManager.SaveScene(scene);
        }

        static void BuildWaitingRoom()
        {
            var scene = NewEnvironment("Waiting room",
                ground: new Color(0.93f, 0.9f, 1f),
                sky: new Color(0.75f, 0.68f, 0.95f),
                horizon: new Color(1f, 0.84f, 0.9f),
                sun: new Color(1f, 0.95f, 0.97f), sunIntensity: 0.9f, sunAngles: new Vector3(55f, 20f, 0f));
            Dreamy();

            var decoration = new GameObject("Decoration").transform;
            Shape(PrimitiveType.Cylinder, "Platform", new Vector3(0f, 0.02f, 0f), new Vector3(5f, 0.02f, 5f),
                decoration, "Waiting platform", new Color(0.82f, 0.76f, 0.98f));
            FloatingShapes(decoration,
                new Color(1f, 0.72f, 0.82f), new Color(0.72f, 0.85f, 1f),
                new Color(0.8f, 1f, 0.85f), new Color(1f, 0.93f, 0.7f));
            Sign(decoration, "No world chosen yet",
                "Take a deep breath and relax.\nYour world will appear as soon as the operator picks one.",
                new Color(0.42f, 0.3f, 0.7f), new Color(0.35f, 0.32f, 0.5f));
            Save(scene, "WaitingRoom");
        }

        // A placeholder for the sponsor's world: none of their content, just
        // a clear sign that "sponsor" was picked. Replaced by their scene in
        // EnvironmentSceneLoader once it's integrated.
        static void BuildSponsorComingSoon()
        {
            var scene = NewEnvironment("Sponsor coming soon",
                ground: new Color(0.88f, 0.96f, 0.95f),
                sky: new Color(0.45f, 0.75f, 0.82f),
                horizon: new Color(1f, 0.9f, 0.72f),
                sun: new Color(1f, 0.95f, 0.85f), sunIntensity: 1f, sunAngles: new Vector3(50f, -25f, 0f));
            Dreamy();

            var decoration = new GameObject("Decoration").transform;
            Shape(PrimitiveType.Cylinder, "Platform", new Vector3(0f, 0.02f, 0f), new Vector3(5f, 0.02f, 5f),
                decoration, "Sponsor platform", new Color(0.62f, 0.86f, 0.86f));
            FloatingShapes(decoration,
                new Color(0.35f, 0.75f, 0.78f), new Color(1f, 0.8f, 0.35f),
                new Color(0.55f, 0.88f, 0.8f), new Color(1f, 0.9f, 0.6f));
            Sign(decoration, "Coming soon",
                "The sponsor's world will appear here.\nThanks for your patience!",
                new Color(0.12f, 0.45f, 0.5f), new Color(0.25f, 0.35f, 0.4f));
            Save(scene, "SponsorComingSoon");
        }

        static void BuildBeach()
        {
            var scene = NewEnvironment("Beach",
                ground: new Color(0.93f, 0.84f, 0.62f),
                sky: new Color(0.45f, 0.7f, 1f),
                horizon: new Color(0.78f, 0.87f, 0.95f),
                sun: new Color(1f, 0.96f, 0.85f), sunIntensity: 1.3f, sunAngles: new Vector3(50f, -30f, 0f));

            var scenery = new GameObject("Scenery").transform;
            Shape(PrimitiveType.Cube, "Sea", new Vector3(0f, 0.005f, 37.5f), new Vector3(100f, 0.01f, 25f),
                scenery, "Water", new Color(0.1f, 0.45f, 0.75f), smoothness: 0.9f);
            Palm(scenery, -12f, 14f);
            Palm(scenery, 15f, 18f);
            Palm(scenery, -5f, -10f);
            Palm(scenery, 20f, -4f);

            // Walking towards the sea: open sand -> shore -> waterline, each
            // ring windier, more humid and saltier.
            AddZones(EnvironmentId.Beach,
                Zone.Base("beach-open", ZoneType.Hot),
                new Zone("beach-shore", ZoneType.Windy, 0f, 18.5f, 100f, 13f, 10),
                new Zone("beach-waterline", ZoneType.Cool, 0f, 24.5f, 100f, 7f, 20),
                new Zone("beach-dunes", ZoneType.Windy, 16f, 4f, 8f, 8f, 10),
                new Zone("beach-palm-shade", ZoneType.Cool, -5f, -10f, 5f, 5f, 10));
            Save(scene, "Beach");
        }

        static void BuildForest()
        {
            var scene = NewEnvironment("Forest",
                ground: new Color(0.25f, 0.42f, 0.2f),
                sky: new Color(0.5f, 0.68f, 0.75f),
                horizon: new Color(0.62f, 0.72f, 0.66f),
                sun: new Color(1f, 0.95f, 0.85f), sunIntensity: 1f, sunAngles: new Vector3(45f, 40f, 0f));

            var scenery = new GameObject("Scenery").transform;
            Shape(PrimitiveType.Cube, "Stream", new Vector3(12f, 0.005f, 5f), new Vector3(1.5f, 0.01f, 70f),
                scenery, "Water", new Color(0.1f, 0.45f, 0.75f), smoothness: 0.9f);
            var trees = new[]
            {
                new Vector2(-20f, -5f), new Vector2(-18f, 12f), new Vector2(-25f, 25f), new Vector2(-6f, 28f),
                new Vector2(8f, 30f), new Vector2(22f, 24f), new Vector2(24f, 10f), new Vector2(20f, -12f),
                new Vector2(-10f, -18f), new Vector2(6f, -20f), new Vector2(-30f, 5f), new Vector2(30f, 0f),
                new Vector2(0f, 40f), new Vector2(-15f, 38f), new Vector2(15f, 40f),
            };
            foreach (var spot in trees) Tree(scenery, spot.x, spot.y);
            Shape(PrimitiveType.Sphere, "Rain cloud", new Vector3(-15f, 7f, 20f), new Vector3(16f, 2.5f, 16f),
                scenery, "Rain cloud", new Color(0.55f, 0.57f, 0.6f));
            Shape(PrimitiveType.Sphere, "Rain cloud (heavy)", new Vector3(-15f, 6f, 20f), new Vector3(9f, 2.5f, 9f),
                scenery, "Rain cloud heavy", new Color(0.3f, 0.32f, 0.36f));

            // The rain gets heavier towards the middle of the rainy area.
            AddZones(EnvironmentId.Forest,
                Zone.Base("forest-open", ZoneType.Cool),
                new Zone("forest-clearing", ZoneType.Hot, 0f, 12f, 10f, 10f, 10),
                new Zone("forest-rain", ZoneType.Cool, -15f, 20f, 16f, 16f, 10),
                new Zone("forest-rain-heavy", ZoneType.Cool, -15f, 20f, 8f, 8f, 20),
                new Zone("forest-stream", ZoneType.Cool, 12f, 5f, 6f, 70f, 10));
            Save(scene, "Forest");
        }

        static void BuildDesert()
        {
            var scene = NewEnvironment("Desert",
                ground: new Color(0.86f, 0.62f, 0.36f),
                sky: new Color(0.55f, 0.72f, 0.95f),
                horizon: new Color(0.95f, 0.82f, 0.62f),
                sun: new Color(1f, 0.88f, 0.7f), sunIntensity: 1.5f, sunAngles: new Vector3(60f, -20f, 0f));

            var scenery = new GameObject("Scenery").transform;
            var rock = new Color(0.6f, 0.42f, 0.3f);
            // A small cave, open towards the start point: shade at its mouth,
            // cooler still inside.
            Shape(PrimitiveType.Cube, "Cave left wall", new Vector3(-3.2f, 1.5f, 22f), new Vector3(0.4f, 3f, 6.8f), scenery, "Rock", rock);
            Shape(PrimitiveType.Cube, "Cave right wall", new Vector3(3.2f, 1.5f, 22f), new Vector3(0.4f, 3f, 6.8f), scenery, "Rock", rock);
            Shape(PrimitiveType.Cube, "Cave back wall", new Vector3(0f, 1.5f, 25.2f), new Vector3(6.8f, 3f, 0.4f), scenery, "Rock", rock);
            Shape(PrimitiveType.Cube, "Cave roof", new Vector3(0f, 3.1f, 22f), new Vector3(6.8f, 0.2f, 6.8f), scenery, "Rock", rock);
            Shape(PrimitiveType.Sphere, "Rock", new Vector3(-14f, 0.8f, 32f), new Vector3(4f, 2.5f, 3f), scenery, "Rock", rock);
            Shape(PrimitiveType.Sphere, "Rock", new Vector3(18f, 0.8f, 30f), new Vector3(5f, 3f, 4f), scenery, "Rock", rock);
            Shape(PrimitiveType.Sphere, "Rock", new Vector3(25f, 0.6f, -8f), new Vector3(3f, 2f, 3f), scenery, "Rock", rock);
            Shape(PrimitiveType.Sphere, "Rock", new Vector3(-22f, 0.6f, -15f), new Vector3(3.5f, 2f, 2.5f), scenery, "Rock", rock);

            AddZones(EnvironmentId.Desert,
                Zone.Base("desert-open", ZoneType.Hot),
                new Zone("desert-cave-mouth", ZoneType.Cool, 0f, 18.5f, 8f, 3f, 10),
                new Zone("desert-cave-inside", ZoneType.Cool, 0f, 22.5f, 6f, 5f, 20),
                new Zone("desert-rock-shade", ZoneType.Cool, 18f, 26f, 6f, 4f, 10),
                new Zone("desert-ridge", ZoneType.Windy, -22f, 0f, 6f, 12f, 10));
            Save(scene, "Desert");
        }

        // ----------------------------------------------------------- helpers

        static Scene NewEnvironment(string name, Color ground, Color sky, Color horizon,
            Color sun, float sunIntensity, Vector3 sunAngles)
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            var light = new GameObject("Sun").AddComponent<Light>();
            light.type = LightType.Directional;
            light.color = sun;
            light.intensity = sunIntensity;
            light.shadows = LightShadows.Soft;
            light.transform.rotation = Quaternion.Euler(sunAngles);

            var floor = GameObject.CreatePrimitive(PrimitiveType.Plane);
            floor.name = "Ground";
            floor.transform.localScale = new Vector3(10f, 1f, 10f); // 100 x 100 m
            Paint(floor, name + " ground", ground, 0.1f);

            // Where the user appears when this world loads (facing +z).
            new GameObject("Player start").AddComponent<EnvironmentSpawnPoint>();

            // Environment scenes become the active scene when loaded, so these
            // settings apply while the scene is showing.
            var skybox = MaterialAsset(name + " sky", "Skybox/Procedural");
            skybox.SetColor("_SkyTint", sky);
            skybox.SetColor("_GroundColor", horizon);
            RenderSettings.skybox = skybox;
            RenderSettings.sun = light;
            // Fixed colours: ambient light from a skybox needs a lighting bake.
            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = sky * 0.8f;
            RenderSettings.ambientEquatorColor = horizon * 0.6f;
            RenderSettings.ambientGroundColor = ground * 0.4f;
            RenderSettings.fog = true;
            RenderSettings.fogMode = FogMode.Linear;
            RenderSettings.fogColor = horizon;
            RenderSettings.fogStartDistance = 30f;
            RenderSettings.fogEndDistance = 150f;
            return scene;
        }

        static void AddZones(EnvironmentId environment, params Zone[] zones)
        {
            var group = new GameObject("Zones").transform;
            foreach (var zone in zones)
            {
                var zoneObject = new GameObject(zone.Id);
                zoneObject.transform.SetParent(group, false);
                zoneObject.transform.localPosition = new Vector3(zone.Center.x, 0f, zone.Center.y);

                // Tall, so the probe at head height is inside it.
                var box = zoneObject.AddComponent<BoxCollider>();
                box.isTrigger = true;
                box.center = new Vector3(0f, 2f, 0f);
                box.size = new Vector3(zone.Size.x, 4f, zone.Size.y);

                var volume = new SerializedObject(zoneObject.AddComponent<ZoneVolume>());
                volume.FindProperty("zoneId").stringValue = zone.Id;
                volume.FindProperty("zoneType").intValue = (int)zone.Type;
                volume.FindProperty("environment").intValue = (int)environment;
                volume.FindProperty("priority").intValue = zone.Priority;
                volume.ApplyModifiedPropertiesWithoutUndo();

                // The trigger is invisible; this pad shows where the zone is.
                // Higher priority pads sit slightly higher so they don't
                // flicker, and are darker so rings can be told apart.
                if (zone.IsBase) continue;
                var pad = GameObject.CreatePrimitive(PrimitiveType.Cube);
                pad.name = "Marker";
                Object.DestroyImmediate(pad.GetComponent<Collider>());
                pad.transform.SetParent(zoneObject.transform, false);
                pad.transform.localPosition = new Vector3(0f, 0.02f + zone.Priority * 0.002f, 0f);
                pad.transform.localScale = new Vector3(zone.Size.x, 0.02f, zone.Size.y);
                var color = Color.Lerp(ZoneColor(zone.Type), Color.black, zone.Priority / 100f);
                Paint(pad, $"Zone {ZoneTypes.ToWireName(zone.Type)} {zone.Priority}", color, 0.1f);
            }
        }

        // Close, soft fog for the rooms: the floor fades into the sky.
        static void Dreamy()
        {
            RenderSettings.fogStartDistance = 8f;
            RenderSettings.fogEndDistance = 45f;
        }

        // Pastel shapes floating in a ring around the start spot, bobbing
        // and turning slowly (FloatAndSpin).
        static void FloatingShapes(Transform parent, params Color[] colors)
        {
            var kinds = new[] { PrimitiveType.Sphere, PrimitiveType.Cube, PrimitiveType.Capsule, PrimitiveType.Sphere };
            for (var i = 0; i < 10; i++)
            {
                var angle = i * 36f + 18f;
                var distance = i % 2 == 0 ? 6f : 8.5f;
                var position = Quaternion.Euler(0f, angle, 0f) * Vector3.forward * distance + Vector3.up * (1.6f + (i % 3) * 0.8f);
                var size = 0.4f + (i % 3) * 0.2f;
                var color = colors[i % colors.Length];
                var shape = Shape(kinds[i % kinds.Length], "Floating shape", position, Vector3.one * size,
                    parent, $"Pastel {i % colors.Length} {ColorUtility.ToHtmlStringRGB(color)}", color, 0.5f);
                Object.DestroyImmediate(shape.GetComponent<Collider>());
                shape.transform.rotation = Quaternion.Euler(20f * i, 30f * i, 10f * i);
                shape.AddComponent<FloatAndSpin>();
            }
        }

        // A sign 4 m ahead of the start spot at eye height: a soft panel with
        // a title and a line of text. World-space UI, so it shows in the
        // headset too.
        static void Sign(Transform parent, string title, string body, Color titleColor, Color bodyColor)
        {
            var sign = new GameObject("Sign", typeof(RectTransform));
            sign.transform.SetParent(parent, false);
            sign.AddComponent<Canvas>().renderMode = RenderMode.WorldSpace;
            var rect = (RectTransform)sign.transform;
            rect.position = new Vector3(0f, 1.9f, 4f);
            rect.sizeDelta = new Vector2(1300f, 520f);
            rect.localScale = Vector3.one * 0.004f; // 1300 units = 5.2 m wide

            var panel = new GameObject("Panel", typeof(RectTransform)).AddComponent<Image>();
            panel.transform.SetParent(sign.transform, false);
            panel.color = new Color(1f, 1f, 1f, 0.6f);
            panel.rectTransform.anchorMin = Vector2.zero;
            panel.rectTransform.anchorMax = Vector2.one;
            panel.rectTransform.offsetMin = Vector2.zero;
            panel.rectTransform.offsetMax = Vector2.zero;

            Label(sign.transform, title, 120, FontStyle.Bold, titleColor, 110f);
            Label(sign.transform, body, 54, FontStyle.Normal, bodyColor, -100f);
        }

        static void Label(Transform parent, string text, int size, FontStyle style, Color color, float y)
        {
            var label = new GameObject("Text", typeof(RectTransform)).AddComponent<Text>();
            label.transform.SetParent(parent, false);
            label.rectTransform.sizeDelta = new Vector2(1250f, 240f);
            label.rectTransform.anchoredPosition = new Vector2(0f, y);
            label.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            label.fontSize = size;
            label.fontStyle = style;
            label.color = color;
            label.alignment = TextAnchor.MiddleCenter;
            label.horizontalOverflow = HorizontalWrapMode.Wrap;
            label.verticalOverflow = VerticalWrapMode.Overflow;
            label.text = text;
        }

        static Color ZoneColor(ZoneType type) => type switch
        {
            ZoneType.Hot => new Color(1f, 0.35f, 0.2f),
            ZoneType.Cool => new Color(0.3f, 0.6f, 1f),
            ZoneType.Windy => new Color(0.92f, 0.92f, 0.92f),
            _ => new Color(0.5f, 0.5f, 0.5f),
        };

        static void Tree(Transform parent, float x, float z)
        {
            Shape(PrimitiveType.Cylinder, "Tree trunk", new Vector3(x, 1.5f, z), new Vector3(0.4f, 1.5f, 0.4f),
                parent, "Bark", new Color(0.4f, 0.28f, 0.18f));
            Shape(PrimitiveType.Sphere, "Tree top", new Vector3(x, 4f, z), new Vector3(3.5f, 3.5f, 3.5f),
                parent, "Leaves", new Color(0.13f, 0.38f, 0.15f));
        }

        static void Palm(Transform parent, float x, float z)
        {
            Shape(PrimitiveType.Cylinder, "Palm trunk", new Vector3(x, 2f, z), new Vector3(0.35f, 2f, 0.35f),
                parent, "Palm trunk", new Color(0.55f, 0.4f, 0.25f));
            Shape(PrimitiveType.Sphere, "Palm leaves", new Vector3(x, 4.2f, z), new Vector3(3f, 0.8f, 3f),
                parent, "Palm leaves", new Color(0.2f, 0.6f, 0.25f));
        }

        static GameObject Shape(PrimitiveType type, string name, Vector3 position, Vector3 scale,
            Transform parent, string material, Color color, float smoothness = 0.2f)
        {
            var shape = GameObject.CreatePrimitive(type);
            shape.name = name;
            shape.transform.SetParent(parent, false);
            shape.transform.localPosition = position;
            shape.transform.localScale = scale;
            Paint(shape, material, color, smoothness);
            return shape;
        }

        static void Paint(GameObject target, string materialName, Color color, float smoothness)
        {
            var material = MaterialAsset(materialName, "Universal Render Pipeline/Lit");
            material.SetColor("_BaseColor", color);
            material.SetFloat("_Smoothness", smoothness);
            target.GetComponent<Renderer>().sharedMaterial = material;
        }

        // The material file with this name, created if missing. An existing
        // one is reused (not replaced), so anything else using it keeps
        // working and the render pipeline's own settings on it are kept.
        static Material MaterialAsset(string name, string shaderName)
        {
            var path = $"{MaterialFolder}/{name}.mat";
            var material = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (material == null)
            {
                material = new Material(Shader.Find(shaderName));
                AssetDatabase.CreateAsset(material, path);
            }
            else if (material.shader.name != shaderName)
            {
                material.shader = Shader.Find(shaderName);
            }
            EditorUtility.SetDirty(material);
            return material;
        }

        static void Save(Scene scene, string name) => EditorSceneManager.SaveScene(scene, ScenePath(name));

        static string ScenePath(string name) => $"{SceneFolder}/{name}.unity";
    }
}
