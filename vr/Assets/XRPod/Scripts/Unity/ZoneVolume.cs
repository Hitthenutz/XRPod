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
            if (zones.Enter(_definition) == ZoneInputResult.WrongEnvironment)
                Debug.LogWarning($"Zone '{zoneId}' ({environment}) ignored: {zones.Environment} is showing.", this);
        }

        void OnTriggerExit(Collider other)
        {
            if (!enabled || !IsPlayer(other)) return;
            Zones()?.Exit(zoneId);
        }

        // Unity doesn't call OnTriggerExit when a zone is disabled or its
        // scene unloads, so leave it here too. Leaving a zone we're not in
        // is ignored.
        void OnDisable()
        {
            if (_definition != null) Zones()?.Exit(zoneId);
        }

        static bool IsPlayer(Collider other) => other.TryGetComponent<PlayerZoneProbe>(out _);

        ZoneStateTracker Zones()
        {
            var root = VrSystemRoot.Instance;
            return root != null && root.Session != null ? root.Session.Zones : null;
        }
    }
}
