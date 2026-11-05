// Loads the scene for whichever environment is selected.
//
// Environment scenes are loaded additively next to the Bootstrap scene, so
// the XR Origin, the VrSystemRoot and the pod link stay alive across
// switches. Only one environment scene is loaded at a time.
//
// If several requests arrive while a scene is loading, it finishes the
// current load and then goes straight to the newest request.

using System;
using System.Collections;
using UnityEngine;
using UnityEngine.SceneManagement;
using XRPod.VR.Core;

namespace XRPod.VR
{
    public sealed class EnvironmentSceneLoader : MonoBehaviour
    {
        [Serializable]
        public struct EnvironmentScene
        {
            public EnvironmentId environment;
            [Tooltip("Scene name exactly as in File > Build Profiles > Scene List.")]
            public string sceneName;
        }

        [SerializeField] EnvironmentScene[] scenes =
        {
            new EnvironmentScene { environment = EnvironmentId.Beach, sceneName = "Beach" },
            new EnvironmentScene { environment = EnvironmentId.Forest, sceneName = "Forest" },
            new EnvironmentScene { environment = EnvironmentId.Desert, sceneName = "Desert" },
            // Left empty until the sponsor's files are inspected; set it to
            // their (or our wrapper) scene's name.
            new EnvironmentScene { environment = EnvironmentId.Sponsor, sceneName = "" },
        };

        [Tooltip("Seconds to fade to black before a switch, and back after.")]
        [SerializeField] float fadeSeconds = 0.3f;

        EnvironmentId _wanted;
        string _loadedScene;
        bool _loading;
        EnvironmentController _environments;
        ScreenFader _fader;

        void Awake() => _fader = ScreenFader.Create(transform);

        void OnEnable()
        {
            var root = VrSystemRoot.Instance;
            if (root == null)
            {
                Debug.LogError("EnvironmentSceneLoader needs a VrSystemRoot in the same scene.", this);
                return;
            }
            _environments = root.Session.Environments;
            _environments.EnvironmentChanged += OnEnvironmentChanged;
        }

        void OnDisable()
        {
            if (_environments != null) _environments.EnvironmentChanged -= OnEnvironmentChanged;
            _environments = null;
        }

        void OnEnvironmentChanged(EnvironmentChangedEvent e)
        {
            _wanted = e.Current;
            if (!_loading) StartCoroutine(LoadWanted());
        }

        IEnumerator LoadWanted()
        {
            _loading = true;
            while (true)
            {
                var target = _wanted;
                var sceneName = SceneFor(target);
                if (sceneName == null)
                {
                    Debug.LogError($"No scene set for {target} in EnvironmentSceneLoader.", this);
                }
                else if (sceneName != _loadedScene)
                {
                    // Start black at launch; otherwise fade out the old world.
                    if (_loadedScene == null) _fader.Alpha = 1f;
                    else yield return _fader.FadeTo(1f, fadeSeconds);

                    yield return UnloadOtherEnvironments(sceneName);
                    _loadedScene = null;

                    // Already open, e.g. you opened it next to Bootstrap in the Editor.
                    if (!SceneManager.GetSceneByName(sceneName).isLoaded)
                    {
                        var load = SceneManager.LoadSceneAsync(sceneName, LoadSceneMode.Additive);
                        if (load == null)
                        {
                            Debug.LogError($"Couldn't load scene '{sceneName}'. Is it in the Build Profile's scene list?", this);
                            if (_wanted == target) break;
                            continue;
                        }
                        yield return load;
                    }

                    var scene = SceneManager.GetSceneByName(sceneName);
                    SceneManager.SetActiveScene(scene);
                    PlacePlayer(scene);
                    _loadedScene = sceneName;
                }

                if (_wanted == target) break; // nothing newer asked for while loading
            }
            // Stays black while newer requests are still loading, then fades
            // in once, on the last one.
            yield return _fader.FadeTo(0f, fadeSeconds);
            _loading = false;
        }

        // Moves the player to the scene's EnvironmentSpawnPoint (or the
        // origin, facing +Z). It moves the camera's rig, keeping the head's
        // offset inside it: in VR that's where the user physically stands.
        static void PlacePlayer(Scene scene)
        {
            var head = Camera.main != null ? Camera.main.transform : null;
            if (head == null) return;

            var spawn = FindSpawnPoint(scene);
            var position = spawn != null ? spawn.position : Vector3.zero;
            var yaw = spawn != null ? spawn.eulerAngles.y : 0f;

            var rig = head.root;
            if (rig == head) // a camera without a rig: just move it
            {
                head.position = new Vector3(position.x, head.position.y, position.z);
                head.rotation = Quaternion.Euler(head.eulerAngles.x, yaw, 0f);
                return;
            }
            rig.RotateAround(head.position, Vector3.up, yaw - head.eulerAngles.y);
            var shift = position - head.position;
            rig.position = new Vector3(rig.position.x + shift.x, position.y, rig.position.z + shift.z);
        }

        static Transform FindSpawnPoint(Scene scene)
        {
            foreach (var root in scene.GetRootGameObjects())
            {
                var spawn = root.GetComponentInChildren<EnvironmentSpawnPoint>();
                if (spawn != null) return spawn.transform;
            }
            return null;
        }

        // Unloads every environment scene except `keep`, including one left
        // open in the Editor next to Bootstrap, so only one world shows.
        IEnumerator UnloadOtherEnvironments(string keep)
        {
            foreach (var entry in scenes)
            {
                if (string.IsNullOrEmpty(entry.sceneName) || entry.sceneName == keep) continue;
                var scene = SceneManager.GetSceneByName(entry.sceneName);
                if (scene.isLoaded) yield return SceneManager.UnloadSceneAsync(scene);
            }
        }

        string SceneFor(EnvironmentId environment)
        {
            foreach (var entry in scenes)
                if (entry.environment == environment && !string.IsNullOrEmpty(entry.sceneName))
                    return entry.sceneName;
            return null;
        }
    }
}
