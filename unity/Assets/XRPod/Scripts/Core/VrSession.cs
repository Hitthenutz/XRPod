// Wires the VR logic together for one run of the app:
//   pod link --environment request--> EnvironmentController
//   EnvironmentController / ZoneStateTracker --changes--> pod link
//
// It publishes one PodStateMessage per real change. Clearing zones because
// the environment changed doesn't get a message of its own; the
// environment change that follows already reports "new environment,
// neutral".
//
// Unity never drives the hardware: it reports where the user is, and the
// Pi decides (manual or automatic mode) whether to act on it.

using System;

namespace XRPod.VR.Core
{
    public sealed class VrSession : IDisposable
    {
        readonly IPodLink _link;
        long _seq;

        public VrSession(IPodLink link, string sessionId = null)
        {
            _link = link ?? throw new ArgumentNullException(nameof(link));
            SessionId = sessionId ?? Guid.NewGuid().ToString("N").Substring(0, 12);
            Zones = new ZoneStateTracker();
            Environments = new EnvironmentController(Zones);

            Zones.ActiveZoneChanged += OnZoneChanged;
            Environments.EnvironmentChanged += OnEnvironmentChanged;
            _link.EnvironmentRequested += OnEnvironmentRequested;
        }

        // Warnings worth logging, e.g. an unknown environment from the pod.
        // Unity forwards these to Debug.LogWarning.
        public event Action<string> Diagnostic;

        public string SessionId { get; }
        public ZoneStateTracker Zones { get; }
        public EnvironmentController Environments { get; }
        public PodStateMessage LastPublished { get; private set; }

        public void Dispose()
        {
            Zones.ActiveZoneChanged -= OnZoneChanged;
            Environments.EnvironmentChanged -= OnEnvironmentChanged;
            _link.EnvironmentRequested -= OnEnvironmentRequested;
        }

        void OnEnvironmentRequested(string name)
        {
            var result = Environments.Request(name, "pod");
            if (result == EnvironmentRequestResult.Invalid)
                Diagnostic?.Invoke($"Pod asked for unknown environment '{name}'; ignored.");
            else if (result == EnvironmentRequestResult.Unavailable)
                Diagnostic?.Invoke($"Pod asked for '{name}', which isn't available in this build; ignored.");
        }

        void OnEnvironmentChanged(EnvironmentChangedEvent e) => Publish("environment_changed");

        void OnZoneChanged(ZoneChangedEvent e)
        {
            if (e.Reason == ZoneChangeReason.EnvironmentReset) return;
            Publish(e.Reason == ZoneChangeReason.Entered ? "zone_entered" : "zone_exited");
        }

        void Publish(string reason)
        {
            var state = new PodStateMessage
            {
                SessionId = SessionId,
                Environment = EnvironmentIds.ToWireName(Environments.Current),
                ZoneId = Zones.ActiveZone?.Id,
                ZoneType = ZoneTypes.ToWireName(Zones.ActiveZoneType),
                ZoneTracking = Zones.ZoneTrackingEnabled,
                Reason = reason,
            };
            if (state.SameStateAs(LastPublished)) return;

            state.Seq = ++_seq;
            LastPublished = state;
            _link.PublishState(state);
        }
    }
}
