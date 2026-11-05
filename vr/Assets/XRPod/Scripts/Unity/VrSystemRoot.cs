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
        [Tooltip("Where the app starts, until the HUD picks a world. None = the waiting room.")]
        [SerializeField] EnvironmentId startEnvironment = EnvironmentId.None;

        [Tooltip("Optional: a component that implements IPodLink, e.g. HttpPodLink. Empty = run offline.")]
        [SerializeField] MonoBehaviour podLink;

        [Tooltip("Log every zone and environment change to the Console.")]
        [SerializeField] bool logEvents = true;

        [Header("Sponsor environment (see vr/docs/SPONSOR_INTEGRATION.md)")]
        [Tooltip("Can the sponsor's world be picked? It shows the 'coming soon' scene until the sponsor's scene is set in EnvironmentSceneLoader.")]
        [SerializeField] bool sponsorAvailable = true;

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
            var result = Session.Environments.Request(startEnvironment, "startup");
            if (result == EnvironmentRequestResult.Unavailable)
                Debug.LogWarning($"Start Environment {startEnvironment} isn't available; showing the waiting room.", this);
            // Starting in the waiting room isn't a change, so say so ourselves:
            // the Pi then knows the headset is there.
            if (Session.Environments.Current == EnvironmentId.None) Session.PublishCurrent();
        }

        void OnDestroy()
        {
            if (Instance != this) return;
            Session?.Dispose();
            Instance = null;
        }
    }
}
