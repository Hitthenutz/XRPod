// Works out which zone the player is in.
//
// Unity tells it "entered zone X" and "left zone X"; it keeps the set of
// zones the player is currently inside and picks the active one:
//   - overlapping zones: highest priority wins, then the most recent entry
//   - leaving the active zone falls back to the next zone still occupied
//   - no zones left: neutral (ActiveZone == null)
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
        }

        readonly List<Occupied> _occupied = new List<Occupied>();
        long _nextOrder;

        public event Action<ZoneChangedEvent> ActiveZoneChanged;

        // Only zones from this environment are accepted. Set by Reset().
        public EnvironmentId Environment { get; private set; } = EnvironmentId.None;

        // false: every zone is ignored and the player stays neutral, e.g. in
        // the sponsor's environment before we've added zones to it.
        public bool ZoneTrackingEnabled { get; private set; } = true;

        // null means neutral.
        public ZoneDefinition ActiveZone { get; private set; }

        public ZoneType ActiveZoneType => ActiveZone?.Type ?? ZoneType.Neutral;

        public int OccupiedCount => _occupied.Count;

        public ZoneInputResult Enter(ZoneDefinition zone)
        {
            if (zone == null) throw new ArgumentNullException(nameof(zone));
            if (zone.Environment != Environment) return ZoneInputResult.WrongEnvironment;
            if (!ZoneTrackingEnabled) return ZoneInputResult.TrackingDisabled;
            if (IndexOf(zone.Id) >= 0) return ZoneInputResult.Duplicate;

            _occupied.Add(new Occupied { Zone = zone, EnteredOrder = _nextOrder++ });
            return UpdateActive(ZoneChangeReason.Entered);
        }

        public ZoneInputResult Exit(string zoneId)
        {
            var index = IndexOf(zoneId);
            if (index < 0) return ZoneInputResult.NotInside;

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
