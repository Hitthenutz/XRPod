// One environmental zone in a scene: plain data, so the zone logic can be
// tested without Unity. In Unity, a ZoneVolume component builds one of these
// from the values set in the Inspector.

using System;

namespace XRPod.VR.Core
{
    public sealed class ZoneDefinition
    {
        public ZoneDefinition(string id, ZoneType type, EnvironmentId environment, int priority = 0)
        {
            if (string.IsNullOrWhiteSpace(id))
                throw new ArgumentException("A zone needs an id", nameof(id));
            if (environment == EnvironmentId.None)
                throw new ArgumentException($"Zone '{id}' needs an environment", nameof(environment));
            Id = id;
            Type = type;
            Environment = environment;
            Priority = priority;
        }

        // Unique within its environment, e.g. "forest-clearing-wind".
        public string Id { get; }

        public ZoneType Type { get; }

        // The environment (scene) this zone belongs to. Zones from any other
        // environment are ignored, e.g. while the old scene is unloading.
        public EnvironmentId Environment { get; }

        // When zones overlap, the highest priority wins. Equal priorities:
        // the zone entered most recently wins.
        public int Priority { get; }

        public override string ToString() => $"{Id} ({ZoneTypes.ToWireName(Type)})";
    }
}
