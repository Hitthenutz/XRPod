// Menu items that get the project ready for the Meta Quest 3, after the XR
// packages are installed (vr/docs/UNITY_SETUP.md step 2):
//
//   XRPod > Set Up VR Player       puts the XR Interaction Toolkit's player
//                                  (XR Origin: head tracking, controllers,
//                                  thumbstick move/turn, teleport) into
//                                  Bootstrap, with our zone probe on its head,
//                                  and turns off the desktop test player
//   XRPod > Apply Quest Settings   Android settings for the Quest 3: app id,
//                                  64-bit IL2CPP, minimum Android version,
//                                  plain HTTP to the Pi
//
// The OpenXR switches themselves are ticked in Project Settings (step 2).

using System.IO;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace XRPod.VR
{
    static class XRPodQuestSetup
    {
        const string BootstrapPath = "Assets/XRPod/Scenes/Bootstrap.unity";

        // From the XR Interaction Toolkit's Starter Assets sample. The first
        // also brings the input actions and interaction manager.
        static readonly string[] PlayerPrefabs = { "XR Interaction Setup", "XR Origin (XR Rig)" };

        [MenuItem("XRPod/Set Up VR Player")]
        static void SetUpVrPlayer()
        {
            if (EditorApplication.isPlayingOrWillChangePlaymode)
            {
                EditorUtility.DisplayDialog("XRPod", "Stop Play mode first.", "OK");
                return;
            }
            var prefab = FindPlayerPrefab();
            if (prefab == null)
            {
                EditorUtility.DisplayDialog("XRPod",
                    "Couldn't find the XR player. Install the XR Interaction Toolkit and import its " +
                    "Starter Assets sample first (vr/docs/UNITY_SETUP.md, step 2).", "OK");
                return;
            }
            if (!File.Exists(BootstrapPath))
            {
                EditorUtility.DisplayDialog("XRPod", "No Bootstrap scene yet. Run XRPod > Create Test Scenes first.", "OK");
                return;
            }
            if (!EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo()) return;

            var scene = EditorSceneManager.OpenScene(BootstrapPath, OpenSceneMode.Single);
            foreach (var root in scene.GetRootGameObjects())
            {
                if (root.name == prefab.name)
                {
                    EditorUtility.DisplayDialog("XRPod", $"Bootstrap already has {prefab.name}.", "OK");
                    return;
                }
            }

            var player = (GameObject)PrefabUtility.InstantiatePrefab(prefab, scene);
            Camera head = null;
            foreach (var camera in player.GetComponentsInChildren<Camera>(true))
                if (head == null || camera.CompareTag("MainCamera")) head = camera;
            if (head == null)
            {
                Object.DestroyImmediate(player);
                EditorUtility.DisplayDialog("XRPod", $"{prefab.name} has no camera; nothing changed.", "OK");
                return;
            }

            // Our zone probe rides on the headset camera.
            var probe = new GameObject("ZoneProbe");
            probe.transform.SetParent(head.transform, false);
            probe.AddComponent<PlayerZoneProbe>();
            var sphere = probe.GetComponent<SphereCollider>();
            sphere.isTrigger = true;
            sphere.radius = 0.15f;
            var body = probe.GetComponent<Rigidbody>();
            body.isKinematic = true;
            body.useGravity = false;

            // Keyboard and mouse still work in the Editor without a headset.
            var mover = player.AddComponent<DesktopTestMover>();
            var settings = new SerializedObject(mover);
            settings.FindProperty("head").objectReferenceValue = head.transform;
            settings.ApplyModifiedPropertiesWithoutUndo();

            // Two cameras would mean two players: turn the desktop one off.
            foreach (var root in scene.GetRootGameObjects())
                if (root != player && root.GetComponent<DesktopTestMover>() != null) root.SetActive(false);

            EditorSceneManager.SaveScene(scene);
            EditorUtility.DisplayDialog("XRPod",
                $"Added {prefab.name} to Bootstrap with the zone probe on its camera, and turned off the desktop " +
                "test player (still in the scene, just disabled).\n\nIn the Editor without a headset, WASD and the " +
                "right mouse button still move you.", "OK");
        }

        [MenuItem("XRPod/Apply Quest Settings")]
        static void ApplyQuestSettings()
        {
            var android = NamedBuildTarget.Android;
            PlayerSettings.productName = "XRPod";
            PlayerSettings.SetApplicationIdentifier(android, "edu.csus.xrpod");
            PlayerSettings.SetScriptingBackend(android, ScriptingImplementation.IL2CPP);
            PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64; // the Quest is 64-bit only
            PlayerSettings.Android.minSdkVersion = AndroidSdkVersions.AndroidApiLevel32;
            PlayerSettings.insecureHttpOption = InsecureHttpOption.AlwaysAllowed; // the Pi serves plain HTTP
            PlayerSettings.colorSpace = ColorSpace.Linear;
            AssetDatabase.SaveAssets();

            EditorUtility.DisplayDialog("XRPod",
                "Quest settings applied: app name XRPod (edu.csus.xrpod), 64-bit IL2CPP, Android 12L or newer, " +
                "plain HTTP allowed.\n\nNext (vr/docs/UNITY_SETUP.md step 7): File > Build Profiles > Android > " +
                "Switch Platform, then Project Validation > Fix All.", "OK");
        }

        static GameObject FindPlayerPrefab()
        {
            foreach (var name in PlayerPrefabs)
            {
                foreach (var guid in AssetDatabase.FindAssets($"\"{name}\" t:Prefab"))
                {
                    var path = AssetDatabase.GUIDToAssetPath(guid);
                    if (Path.GetFileNameWithoutExtension(path) == name)
                        return AssetDatabase.LoadAssetAtPath<GameObject>(path);
                }
            }
            return null;
        }
    }
}
