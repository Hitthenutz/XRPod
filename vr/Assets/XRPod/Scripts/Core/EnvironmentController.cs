// Decides which environment is showing.
//
// A request (from the Pi, the keyboard in the Editor, or startup) is checked,
// ignored if it's unknown, unavailable or already active, and otherwise:
//   1. clears every zone (the player is back to neutral),
//   2. raises EnvironmentChanged, which the scene loader listens to.
// It doesn't load scenes itself, so it can be tested without Unity.
//
// Each environment has two switches:
//   - available: can it be selected? Off for Sponsor until its files are
//     integrated, so selecting it doesn't leave the user in a missing scene.
//   - zone tracking: are zones detected there? Off for Sponsor until we
//     know whether we can add our own zones to its scene.
// Beach, Forest and Desert are on for both.

using System;
using System.Collections.Generic;

namespace XRPod.VR.Core
{
    public sealed class EnvironmentController
    {
        readonly ZoneStateTracker _zones;
        readonly HashSet<EnvironmentId> _available = new HashSet<EnvironmentId>
            { EnvironmentId.Beach, EnvironmentId.Forest, EnvironmentId.Desert };
        readonly HashSet<EnvironmentId> _zoneTracking = new HashSet<EnvironmentId>
            { EnvironmentId.Beach, EnvironmentId.Forest, EnvironmentId.Desert };

        public EnvironmentController(ZoneStateTracker zones)
        {
            _zones = zones ?? throw new ArgumentNullException(nameof(zones));
        }

        public event Action<EnvironmentChangedEvent> EnvironmentChanged;

        // The zone tracker holds the current environment, so the two can
        // never disagree.
        public EnvironmentId Current => _zones.Environment;

        public bool IsAvailable(EnvironmentId environment) => _available.Contains(environment);

        public bool HasZoneTracking(EnvironmentId environment) => _zoneTracking.Contains(environment);

        // Set these at startup, before the first Request.
        public void SetAvailable(EnvironmentId environment, bool available)
        {
            if (environment == EnvironmentId.None) return;
            if (available) _available.Add(environment);
            else _available.Remove(environment);
        }

        // Takes effect the next time that environment is selected.
        public void SetZoneTracking(EnvironmentId environment, bool enabled)
        {
            if (environment == EnvironmentId.None) return;
            if (enabled) _zoneTracking.Add(environment);
            else _zoneTracking.Remove(environment);
        }

        public EnvironmentRequestResult Request(EnvironmentId environment, string source)
        {
            if (environment == EnvironmentId.None) return EnvironmentRequestResult.Invalid;
            if (!IsAvailable(environment)) return EnvironmentRequestResult.Unavailable;
            if (environment == Current) return EnvironmentRequestResult.AlreadyActive;

            var previous = Current;
            _zones.Reset(environment, HasZoneTracking(environment));
            EnvironmentChanged?.Invoke(new EnvironmentChangedEvent(previous, environment, source));
            return EnvironmentRequestResult.Changed;
        }

        public EnvironmentRequestResult Request(string wireName, string source)
        {
            return EnvironmentIds.TryParse(wireName, out var environment)
                ? Request(environment, source)
                : EnvironmentRequestResult.Invalid;
        }
    }
}
