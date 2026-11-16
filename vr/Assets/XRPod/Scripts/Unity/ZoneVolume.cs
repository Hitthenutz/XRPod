// An environmental zone in a scene. Put it on an object with a trigger
// collider (a Box Collider with Is Trigger ticked) covering the area.
//
// When the PlayerZoneProbe enters or leaves, it tells the session's
// ZoneStateTracker, which handles overlaps and duplicates. This script
// only translates Unity's trigger callbacks.

using UnityEngine;
using XRPod.VR.Core;

namespace XRPod.VR
{
    [RequireComponent(typeof(Collider))]
    public sealed class ZoneVolume : MonoBehaviour
    {
        [Tooltip("Unique within this environment, e.g. forest-clearing-wind.")]
        [SerializeField] string zoneId;

        [SerializeField] ZoneType zoneType = ZoneType.Windy;

        [Tooltip("The environment (scene) this zone is in.")]
        [SerializeField] EnvironmentId environment = EnvironmentId.Forest;

        [Tooltip("When zones overlap, the higher number wins. Equal: the one entered last wins.")]
        [SerializeField] int priority;

        ZoneDefinition _definition;
        bool _inside; // the player is in this volume (and it was counted)
        static bool s_markersVisible;

        // The coloured pads ("Marker" children, from the test scene builder)
        // show where zones are. They're for testing: hidden while playing
        // unless turned on (key Z, EditorTestControls). Zones work either way.
        public static bool MarkersVisible
        {
            get => s_markersVisible;
            set
            {
                s_markersVisible = value;
                foreach (var zone in FindObjectsByType<ZoneVolume>()) zone.ApplyMarker();
            }
        }

        void ApplyMarker()
        {
            var marker = transform.Find("Marker");
            if (marker != null && marker.TryGetComponent<Renderer>(out var pad)) pad.enabled = s_markersVisible;
        }

        // Runs when the component is first added in the Editor.
        void Reset()
        {
            zoneId = gameObject.name;
            GetComponent<Collider>().isTrigger = true;
        }

        void OnValidate()
        {
            var col = GetComponent<Collider>();
            if (col != null && !col.isTrigger)
                Debug.LogWarning($"Zone '{zoneId}': tick Is Trigger on its collider, or the player will bump into it.", this);
        }

        void Awake()
        {
            ApplyMarker();
            if (string.IsNullOrWhiteSpace(zoneId) || environment == EnvironmentId.None)
            {
                Debug.LogError($"{name}: ZoneVolume needs a Zone Id and an Environment. Disabled.", this);
                enabled = false;
                return;
            }
            _definition = new ZoneDefinition(zoneId, zoneType, environment, priority);
        }

        void OnTriggerEnter(Collider other)
        {
            if (!enabled || !IsPlayer(other)) return;
            var zones = Zones();
            if (zones == null) return;
            // Expected briefly while an old scene unloads; if it keeps
            // happening, the zone's Environment field is set wrong.
            var result = zones.Enter(_definition);
            if (result == ZoneInputResult.WrongEnvironment)
                Debug.LogWarning($"Zone '{zoneId}' ({environment}) ignored: {zones.Environment} is showing.", this);
            // Counted (Changed, NoChange, or another volume with this id).
            _inside = result != ZoneInputResult.WrongEnvironment && result != ZoneInputResult.TrackingDisabled;
        }

        void OnTriggerExit(Collider other)
        {
            if (!enabled || !IsPlayer(other) || !_inside) return;
            _inside = false;
            Zones()?.Exit(zoneId);
        }

        // Unity doesn't call OnTriggerExit when a zone is disabled or its
        // scene unloads, so leave it here too, but only if the player was in
        // this volume (other volumes may share the id).
        void OnDisable()
        {
            if (!_inside) return;
            _inside = false;
            Zones()?.Exit(zoneId);
        }

        static bool IsPlayer(Collider other) => other.TryGetComponent<PlayerZoneProbe>(out _);

        ZoneStateTracker Zones()
        {
            var root = VrSystemRoot.Instance;
            return root != null && root.Session != null ? root.Session.Zones : null;
        }
    }
}
