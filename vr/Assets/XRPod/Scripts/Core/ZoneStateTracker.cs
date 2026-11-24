// Works out which zone the player is in.
//
// Unity tells it "entered zone X" and "left zone X"; it keeps the set of
// zones the player is currently inside and picks the active one:
//   - overlapping zones: highest priority wins, then the most recent entry
//   - leaving the active zone falls back to the next zone still occupied
//   - no zones left: neutral (ActiveZone == null)
//   - several volumes may share one id (e.g. shade under every umbrella):
//     the player is in that zone until they've left all of them
// ActiveZoneChanged fires only when the active zone really changes, so
// repeated or overlapping trigger events never produce duplicate events.

using System;
using System.Collections.Generic;

namespace XRPod.VR.Core
{
    public sealed class ZoneStateTracker
    {
        sealed class Occupied
        {
            public ZoneDefinition Zone;
            public long EnteredOrder;
            // The volumes with this id the player is inside (each volume has
            // its own definition). The same one entering twice counts once.
            public readonly List<ZoneDefinition> Volumes = new List<ZoneDefinition>();
        }

        readonly List<Occupied> _occupied = new List<Occupied>();
        long _nextOrder;

        public event Action<ZoneChangedEvent> ActiveZoneChanged;

        // Only zones from this environment are accepted. Set by Reset().
        public EnvironmentId Environment { get; private set; } = EnvironmentId.None;

        // false: every zone is ignored and the player stays neutral, e.g. in
        // the sponsor's environment before we've added zones to it.
        public bool ZoneTrackingEnabled { get; private set; } // nothing to track until a world is chosen

        // null means neutral.
        public ZoneDefinition ActiveZone { get; private set; }

        public ZoneType ActiveZoneType => ActiveZone?.Type ?? ZoneType.Neutral;

        public int OccupiedCount => _occupied.Count;

        public ZoneInputResult Enter(ZoneDefinition zone)
        {
            if (zone == null) throw new ArgumentNullException(nameof(zone));
            if (zone.Environment != Environment) return ZoneInputResult.WrongEnvironment;
            if (!ZoneTrackingEnabled) return ZoneInputResult.TrackingDisabled;
            var index = IndexOf(zone.Id);
            if (index >= 0)
            {
                // Already in a zone with this id: remember another volume of
                // it (not the same one twice).
                var volumes = _occupied[index].Volumes;
                if (!volumes.Contains(zone)) volumes.Add(zone);
                return ZoneInputResult.Duplicate;
            }

            var entry = new Occupied { Zone = zone, EnteredOrder = _nextOrder++ };
            entry.Volumes.Add(zone);
            _occupied.Add(entry);
            return UpdateActive(ZoneChangeReason.Entered);
        }

        public ZoneInputResult Exit(string zoneId)
        {
            var index = IndexOf(zoneId);
            if (index < 0) return ZoneInputResult.NotInside;

            // Still inside another volume with this id: no change.
            var volumes = _occupied[index].Volumes;
            volumes.RemoveAt(volumes.Count - 1);
            if (volumes.Count > 0) return ZoneInputResult.NoChange;

            _occupied.RemoveAt(index);
            return UpdateActive(ZoneChangeReason.Exited);
        }

        // Forget every zone and switch to a new environment. Call this when
        // the environment changes: the old scene's triggers won't send exits.
        public void Reset(EnvironmentId environment, bool zoneTracking = true)
        {
            _occupied.Clear();
            var previous = ActiveZone;
            ActiveZone = null;
            if (previous != null)
                ActiveZoneChanged?.Invoke(new ZoneChangedEvent(Environment, previous, null, ZoneChangeReason.EnvironmentReset));
            Environment = environment;
            ZoneTrackingEnabled = zoneTracking;
        }

        int IndexOf(string zoneId)
        {
            for (var i = 0; i < _occupied.Count; i++)
                if (_occupied[i].Zone.Id == zoneId) return i;
            return -1;
        }

        ZoneInputResult UpdateActive(ZoneChangeReason reason)
        {
            Occupied best = null;
            foreach (var entry in _occupied)
            {
                if (best == null
                    || entry.Zone.Priority > best.Zone.Priority
                    || (entry.Zone.Priority == best.Zone.Priority && entry.EnteredOrder > best.EnteredOrder))
                    best = entry;
            }

            var next = best?.Zone;
            if (next == ActiveZone) return ZoneInputResult.NoChange;

            var previous = ActiveZone;
            ActiveZone = next;
            ActiveZoneChanged?.Invoke(new ZoneChangedEvent(Environment, previous, next, reason));
            return ZoneInputResult.Changed;
        }
    }
}
