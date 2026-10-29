// The one object that owns the VR session. Put it in the Bootstrap scene
// (the scene that is never unloaded, next to the XR Origin).
//
// Other scripts reach the session through VrSystemRoot.Instance.Session.

using UnityEngine;
using XRPod.VR.Core;

namespace XRPod.VR
{
    [DefaultExecutionOrder(-100)] // set up before any ZoneVolume or loader
    public sealed class VrSystemRoot : MonoBehaviour
    {
        [Tooltip("Environment to show when the app starts, until the pod asks for another one.")]
        [SerializeField] EnvironmentId startEnvironment = EnvironmentId.Forest;

        [Tooltip("Optional: a component that implements IPodLink, e.g. HttpPodLink. Empty = run offline.")]
        [SerializeField] MonoBehaviour podLink;

        [Tooltip("Log every zone and environment change to the Console.")]
        [SerializeField] bool logEvents = true;

        [Header("Sponsor environment (see unity/docs/SPONSOR_INTEGRATION.md)")]
        [Tooltip("Tick once the sponsor's scene is in the project and set in EnvironmentSceneLoader.")]
        [SerializeField] bool sponsorAvailable;

        [Tooltip("Tick once our ZoneVolumes have been added to the sponsor's scene.")]
        [SerializeField] bool sponsorZoneTracking;

        public static VrSystemRoot Instance { get; private set; }

        public VrSession Session { get; private set; }

        // Set when running offline (no pod link), so test tools can pretend
        // the pod sent a request. null when a real link is in use.
        public InMemoryPodLink OfflineLink { get; private set; }

        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Debug.LogWarning("A second VrSystemRoot was found and removed. Keep exactly one, in the Bootstrap scene.", this);
                Destroy(gameObject);
                return;
            }
            Instance = this;

            var link = podLink as IPodLink;
            if (podLink != null && link == null)
                Debug.LogError($"{podLink.GetType().Name} doesn't implement IPodLink; running offline.", this);

            if (link == null) link = OfflineLink = new InMemoryPodLink();
            Session = new VrSession(link);
            Session.Environments.SetAvailable(EnvironmentId.Sponsor, sponsorAvailable);
            Session.Environments.SetZoneTracking(EnvironmentId.Sponsor, sponsorZoneTracking);
            Session.Diagnostic += message => Debug.LogWarning($"[XRPod] {message}", this);
            if (logEvents)
            {
                Session.Environments.EnvironmentChanged += e => Debug.Log($"[XRPod] {e}");
                Session.Zones.ActiveZoneChanged += e => Debug.Log($"[XRPod] {e}");
            }
        }

        void Start()
        {
            if (Session.Environments.Request(startEnvironment, "startup") == EnvironmentRequestResult.Unavailable)
                Debug.LogWarning($"Start Environment {startEnvironment} isn't available; waiting for a selection.", this);
        }

        void OnDestroy()
        {
            if (Instance != this) return;
            Session?.Dispose();
            Instance = null;
        }
    }
}
