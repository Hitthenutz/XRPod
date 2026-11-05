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

        EnvironmentId _wanted;
        string _loadedScene;
        bool _loading;
        EnvironmentController _environments;

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
                    if (_loadedScene != null && SceneManager.GetSceneByName(_loadedScene).isLoaded)
                        yield return SceneManager.UnloadSceneAsync(_loadedScene);
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

                    SceneManager.SetActiveScene(SceneManager.GetSceneByName(sceneName));
                    _loadedScene = sceneName;
                }

                if (_wanted == target) break; // nothing newer asked for while loading
            }
            _loading = false;
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
