// Events raised when the active zone or the environment changes, and the
// result codes the trackers return so callers can log what happened.

namespace XRPod.VR.Core
{
    public enum ZoneChangeReason
    {
        Entered,          // the player walked into a zone that is now active
        Exited,           // the player left the active zone
        EnvironmentReset, // the environment changed, so every zone was cleared
    }

    public sealed class ZoneChangedEvent
    {
        public ZoneChangedEvent(EnvironmentId environment, ZoneDefinition previous, ZoneDefinition current, ZoneChangeReason reason)
        {
            Environment = environment;
            Previous = previous;
            Current = current;
            Reason = reason;
        }

        public EnvironmentId Environment { get; }

        // null means neutral (no zone).
        public ZoneDefinition Previous { get; }
        public ZoneDefinition Current { get; }

        public ZoneChangeReason Reason { get; }

        public ZoneType CurrentType => Current?.Type ?? ZoneType.Neutral;

        public override string ToString() =>
            $"[{EnvironmentIds.ToWireName(Environment)}] zone {Previous?.ToString() ?? "neutral"} -> {Current?.ToString() ?? "neutral"} ({Reason})";
    }

    public sealed class EnvironmentChangedEvent
    {
        public EnvironmentChangedEvent(EnvironmentId previous, EnvironmentId current, string source)
        {
            Previous = previous;
            Current = current;
            Source = source;
        }

        public EnvironmentId Previous { get; }
        public EnvironmentId Current { get; }

        // Who asked for it: "pod", "startup", "keyboard", ...
        public string Source { get; }

        public override string ToString() =>
            $"environment {EnvironmentIds.ToWireName(Previous)} -> {EnvironmentIds.ToWireName(Current)} (from {Source})";
    }

    public enum ZoneInputResult
    {
        Changed,          // accepted, and the active zone changed
        NoChange,         // accepted, but another zone is still the active one
        Duplicate,        // already inside this zone: ignored
        NotInside,        // exit for a zone we weren't in: ignored
        WrongEnvironment, // zone belongs to another environment: ignored
        TrackingDisabled, // zone tracking is off in this environment: ignored
    }

    public enum EnvironmentRequestResult
    {
        Changed,
        AlreadyActive, // asked for the environment that's already showing: ignored
        Invalid,       // unknown name or "none": ignored
        Unavailable,   // known, but not in this build yet (e.g. sponsor): ignored
    }
}
