// Tests for zone tracking, environment switching and what gets reported
// to the pod. Each test builds a fresh session with an in-memory pod link.

using System;
using System.Collections.Generic;
using XRPod.VR.Core;

namespace XRPod.VR.OfflineTests
{
    sealed class TestCase
    {
        public TestCase(string name, Action run) { Name = name; Run = run; }
        public string Name { get; }
        public Action Run { get; }
    }

    // Records everything a session raises, so tests can count events.
    sealed class Harness
    {
        public readonly InMemoryPodLink Link = new InMemoryPodLink();
        public readonly VrSession Session;
        public readonly List<ZoneChangedEvent> ZoneEvents = new List<ZoneChangedEvent>();
        public readonly List<EnvironmentChangedEvent> EnvironmentEvents = new List<EnvironmentChangedEvent>();
        public readonly List<string> Diagnostics = new List<string>();

        public Harness(EnvironmentId start = EnvironmentId.Forest)
        {
            Session = new VrSession(Link, "test");
            Session.Zones.ActiveZoneChanged += ZoneEvents.Add;
            Session.Environments.EnvironmentChanged += EnvironmentEvents.Add;
            Session.Diagnostic += Diagnostics.Add;
            if (start != EnvironmentId.None)
            {
                Session.Environments.Request(start, "startup");
                ClearRecorded();
            }
        }

        public ZoneStateTracker Zones => Session.Zones;
        public EnvironmentController Environments => Session.Environments;

        public void ClearRecorded()
        {
            ZoneEvents.Clear();
            EnvironmentEvents.Clear();
            Link.Published.Clear();
        }
    }

    static class Tests
    {
        static readonly ZoneDefinition ForestWind = new ZoneDefinition("forest-wind", ZoneType.Windy, EnvironmentId.Forest);
        static readonly ZoneDefinition ForestSun = new ZoneDefinition("forest-sun", ZoneType.Hot, EnvironmentId.Forest);
        static readonly ZoneDefinition ForestCave = new ZoneDefinition("forest-cave", ZoneType.Cool, EnvironmentId.Forest, priority: 10);
        static readonly ZoneDefinition BeachSun = new ZoneDefinition("beach-sun", ZoneType.Hot, EnvironmentId.Beach);

        public static readonly TestCase[] All =
        {
            // ---------------------------------------------------- basics
            new TestCase("starts neutral with no environment", () =>
            {
                var h = new Harness(EnvironmentId.None);
                Equal(EnvironmentId.None, h.Environments.Current, "environment");
                Equal(null, h.Zones.ActiveZone, "active zone");
                Equal(ZoneType.Neutral, h.Zones.ActiveZoneType, "zone type");
            }),

            new TestCase("zones are ignored before any environment is chosen", () =>
            {
                var h = new Harness(EnvironmentId.None);
                Equal(ZoneInputResult.WrongEnvironment, h.Zones.Enter(ForestWind), "enter result");
                Equal(0, h.ZoneEvents.Count, "zone events");
            }),

            new TestCase("entering a zone makes it active, with one event", () =>
            {
                var h = new Harness();
                Equal(ZoneInputResult.Changed, h.Zones.Enter(ForestWind), "enter result");
                Equal(ForestWind, h.Zones.ActiveZone, "active zone");
                Equal(1, h.ZoneEvents.Count, "zone events");
                Equal(null, h.ZoneEvents[0].Previous, "previous");
                Equal(ZoneChangeReason.Entered, h.ZoneEvents[0].Reason, "reason");
            }),

            new TestCase("leaving the only zone returns to neutral", () =>
            {
                var h = new Harness();
                h.Zones.Enter(ForestWind);
                Equal(ZoneInputResult.Changed, h.Zones.Exit("forest-wind"), "exit result");
                Equal(null, h.Zones.ActiveZone, "active zone");
                Equal(ZoneType.Neutral, h.Zones.ActiveZoneType, "zone type");
                Equal(2, h.ZoneEvents.Count, "zone events");
                Equal(ZoneChangeReason.Exited, h.ZoneEvents[1].Reason, "reason");
            }),

            // ------------------------------------------------ duplicates
            new TestCase("entering the same zone twice gives one event", () =>
            {
                var h = new Harness();
                h.Zones.Enter(ForestWind);
                Equal(ZoneInputResult.Duplicate, h.Zones.Enter(ForestWind), "second enter");
                Equal(1, h.ZoneEvents.Count, "zone events");
                Equal(1, h.Zones.OccupiedCount, "occupied");
            }),

            new TestCase("leaving a zone you're not in is ignored", () =>
            {
                var h = new Harness();
                Equal(ZoneInputResult.NotInside, h.Zones.Exit("forest-wind"), "exit result");
                h.Zones.Enter(ForestWind);
                h.Zones.Exit("forest-wind");
                Equal(ZoneInputResult.NotInside, h.Zones.Exit("forest-wind"), "second exit");
                Equal(2, h.ZoneEvents.Count, "zone events");
            }),

            // ------------------------------------------------- overlaps
            new TestCase("overlap: newest zone wins, leaving it falls back to the older one", () =>
            {
                var h = new Harness();
                h.Zones.Enter(ForestWind);
                h.Zones.Enter(ForestSun);
                Equal(ForestSun, h.Zones.ActiveZone, "after entering both");
                h.Zones.Exit("forest-sun");
                Equal(ForestWind, h.Zones.ActiveZone, "after leaving sun");
                h.Zones.Exit("forest-wind");
                Equal(null, h.Zones.ActiveZone, "after leaving both");
                Equal(4, h.ZoneEvents.Count, "zone events");
            }),

            new TestCase("overlap: leaving the older zone first changes nothing", () =>
            {
                var h = new Harness();
                h.Zones.Enter(ForestWind);
                h.Zones.Enter(ForestSun);
                Equal(ZoneInputResult.NoChange, h.Zones.Exit("forest-wind"), "exit wind");
                Equal(ForestSun, h.Zones.ActiveZone, "active zone");
                Equal(2, h.ZoneEvents.Count, "zone events");
                h.Zones.Exit("forest-sun");
                Equal(null, h.Zones.ActiveZone, "after leaving sun");
            }),

            new TestCase("overlap: higher priority wins even if entered first", () =>
            {
                var h = new Harness();
                h.Zones.Enter(ForestCave);
                Equal(ZoneInputResult.NoChange, h.Zones.Enter(ForestWind), "enter wind inside cave");
                Equal(ForestCave, h.Zones.ActiveZone, "active zone");
                h.Zones.Exit("forest-cave");
                Equal(ForestWind, h.Zones.ActiveZone, "after leaving cave");
                Equal(2, h.ZoneEvents.Count, "zone events");
            }),

            // ------------------------------------------- environments
            new TestCase("switching environment resets the zone to neutral", () =>
            {
                var h = new Harness();
                h.Zones.Enter(ForestWind);
                h.Zones.Enter(ForestSun);
                h.ClearRecorded();

                Equal(EnvironmentRequestResult.Changed, h.Environments.Request(EnvironmentId.Beach, "test"), "request");
                Equal(EnvironmentId.Beach, h.Environments.Current, "environment");
                Equal(null, h.Zones.ActiveZone, "active zone");
                Equal(0, h.Zones.OccupiedCount, "occupied");
                Equal(1, h.ZoneEvents.Count, "zone events");
                Equal(ZoneChangeReason.EnvironmentReset, h.ZoneEvents[0].Reason, "reason");
                Equal(EnvironmentId.Forest, h.ZoneEvents[0].Environment, "reset reports the old environment");
                Equal(1, h.EnvironmentEvents.Count, "environment events");
            }),

            new TestCase("switching from neutral raises no zone event", () =>
            {
                var h = new Harness();
                h.Environments.Request(EnvironmentId.Desert, "test");
                Equal(0, h.ZoneEvents.Count, "zone events");
                Equal(1, h.EnvironmentEvents.Count, "environment events");
            }),

            new TestCase("old scene's zones are ignored after a switch", () =>
            {
                var h = new Harness();
                h.Zones.Enter(ForestWind);
                h.Environments.Request(EnvironmentId.Beach, "test");
                h.ClearRecorded();

                // The old scene unloading, or the player brushing a forest
                // zone before it's gone.
                Equal(ZoneInputResult.NotInside, h.Zones.Exit("forest-wind"), "late exit");
                Equal(ZoneInputResult.WrongEnvironment, h.Zones.Enter(ForestSun), "late enter");
                Equal(0, h.ZoneEvents.Count, "zone events");

                Equal(ZoneInputResult.Changed, h.Zones.Enter(BeachSun), "new scene's zone");
                Equal(BeachSun, h.Zones.ActiveZone, "active zone");
            }),

            new TestCase("asking for the current environment again is ignored", () =>
            {
                var h = new Harness();
                h.Zones.Enter(ForestWind);
                Equal(EnvironmentRequestResult.AlreadyActive, h.Environments.Request(EnvironmentId.Forest, "test"), "request");
                Equal(ForestWind, h.Zones.ActiveZone, "zone kept");
                Equal(0, h.EnvironmentEvents.Count, "environment events");
            }),

            new TestCase("environment names: case and spaces ok, unknown and none rejected", () =>
            {
                var h = new Harness();
                Equal(EnvironmentRequestResult.Changed, h.Environments.Request(" Beach ", "test"), "' Beach '");
                Equal(EnvironmentRequestResult.Invalid, h.Environments.Request("moon", "test"), "moon");
                Equal(EnvironmentRequestResult.Invalid, h.Environments.Request("none", "test"), "none");
                Equal(EnvironmentRequestResult.Invalid, h.Environments.Request((string)null, "test"), "null");
                Equal(EnvironmentId.Beach, h.Environments.Current, "environment");
            }),

            // ------------------------------------- reporting to the pod
            new TestCase("pod gets one message per change, numbered in order", () =>
            {
                var h = new Harness(EnvironmentId.None);
                h.Environments.Request(EnvironmentId.Forest, "startup");
                h.Zones.Enter(ForestWind);
                h.Zones.Enter(ForestWind); // duplicate: no message
                h.Zones.Exit("forest-wind");

                var sent = h.Link.Published;
                Equal(3, sent.Count, "messages");
                Equal("environment_changed", sent[0].Reason, "1st reason");
                Equal("zone_entered", sent[1].Reason, "2nd reason");
                Equal("windy", sent[1].ZoneType, "2nd zone type");
                Equal("zone_exited", sent[2].Reason, "3rd reason");
                Equal("neutral", sent[2].ZoneType, "3rd zone type");
                Equal(null, sent[2].ZoneId, "3rd zone id");
                Equal(1L, sent[0].Seq, "1st seq");
                Equal(3L, sent[2].Seq, "3rd seq");
            }),

            new TestCase("overlap changes that don't move the active zone send nothing", () =>
            {
                var h = new Harness();
                h.Zones.Enter(ForestCave);
                h.Zones.Enter(ForestWind);
                h.Zones.Exit("forest-wind");
                Equal(1, h.Link.Published.Count, "messages");
            }),

            new TestCase("switching environment sends one message, not a reset first", () =>
            {
                var h = new Harness();
                h.Zones.Enter(ForestWind);
                h.ClearRecorded();
                h.Environments.Request(EnvironmentId.Desert, "test");

                Equal(1, h.Link.Published.Count, "messages");
                var m = h.Link.Last;
                Equal("desert", m.Environment, "environment");
                Equal("neutral", m.ZoneType, "zone type");
                Equal(null, m.ZoneId, "zone id");
            }),

            new TestCase("a request from the pod switches the environment", () =>
            {
                var h = new Harness();
                h.Link.SimulateEnvironmentRequest("beach");
                Equal(EnvironmentId.Beach, h.Environments.Current, "environment");
                Equal("pod", h.EnvironmentEvents[0].Source, "source");
                Equal("beach", h.Link.Last.Environment, "reported");
            }),

            new TestCase("an unknown request from the pod is ignored and logged", () =>
            {
                var h = new Harness();
                h.Link.SimulateEnvironmentRequest("moon");
                Equal(EnvironmentId.Forest, h.Environments.Current, "environment");
                Equal(0, h.Link.Published.Count, "messages");
                Equal(1, h.Diagnostics.Count, "diagnostics");
            }),

            new TestCase("message JSON matches the proposed format", () =>
            {
                var m = new PodStateMessage
                {
                    SessionId = "abc", Seq = 7, Environment = "forest",
                    ZoneId = "clearing \"wind\"", ZoneType = "windy", ZoneTracking = true, Reason = "zone_entered",
                };
                Equal("{\"session_id\":\"abc\",\"seq\":7,\"environment\":\"forest\",\"zone_id\":\"clearing \\\"wind\\\"\"," +
                      "\"zone_type\":\"windy\",\"zone_tracking\":true,\"reason\":\"zone_entered\"}",
                    m.ToJson(), "json");
                m.ZoneId = null;
                Contains(m.ToJson(), "\"zone_id\":null", "null zone id");
            }),

            new TestCase("disposing the session stops listening to the pod", () =>
            {
                var h = new Harness();
                h.Session.Dispose();
                h.Link.SimulateEnvironmentRequest("beach");
                Equal(EnvironmentId.Forest, h.Environments.Current, "environment");
            }),

            // ------------------------------------------ sponsor environment
            new TestCase("sponsor: unavailable until enabled, request ignored and logged", () =>
            {
                var h = new Harness();
                h.Zones.Enter(ForestWind);
                h.ClearRecorded();

                Equal(EnvironmentRequestResult.Unavailable, h.Environments.Request(EnvironmentId.Sponsor, "test"), "direct request");
                h.Link.SimulateEnvironmentRequest("sponsor");
                Equal(EnvironmentId.Forest, h.Environments.Current, "environment");
                Equal(ForestWind, h.Zones.ActiveZone, "zone kept");
                Equal(0, h.Link.Published.Count, "messages");
                Equal(1, h.Diagnostics.Count, "diagnostics");
            }),

            new TestCase("sponsor: selecting it resets zones and reports zone tracking off", () =>
            {
                var h = new Harness();
                h.Environments.SetAvailable(EnvironmentId.Sponsor, true);
                h.Zones.Enter(ForestWind);
                h.ClearRecorded();

                h.Link.SimulateEnvironmentRequest("sponsor");
                Equal(EnvironmentId.Sponsor, h.Environments.Current, "environment");
                Equal(null, h.Zones.ActiveZone, "zone");
                Equal(false, h.Zones.ZoneTrackingEnabled, "tracking");
                Equal(1, h.Link.Published.Count, "messages");
                Equal("sponsor", h.Link.Last.Environment, "reported environment");
                Equal(false, h.Link.Last.ZoneTracking, "reported tracking");
            }),

            new TestCase("sponsor: zones are ignored while zone tracking is off", () =>
            {
                var h = new Harness();
                h.Environments.SetAvailable(EnvironmentId.Sponsor, true);
                h.Environments.Request(EnvironmentId.Sponsor, "test");
                h.ClearRecorded();

                var sponsorZone = new ZoneDefinition("sponsor-wind", ZoneType.Windy, EnvironmentId.Sponsor);
                Equal(ZoneInputResult.TrackingDisabled, h.Zones.Enter(sponsorZone), "enter");
                Equal(ZoneInputResult.NotInside, h.Zones.Exit("sponsor-wind"), "exit");
                Equal(0, h.ZoneEvents.Count, "zone events");
                Equal(0, h.Link.Published.Count, "messages");
            }),

            new TestCase("sponsor: zones work once zone tracking is turned on", () =>
            {
                var h = new Harness();
                h.Environments.SetAvailable(EnvironmentId.Sponsor, true);
                h.Environments.SetZoneTracking(EnvironmentId.Sponsor, true);
                h.Environments.Request(EnvironmentId.Sponsor, "test");

                var sponsorZone = new ZoneDefinition("sponsor-wind", ZoneType.Windy, EnvironmentId.Sponsor);
                Equal(ZoneInputResult.Changed, h.Zones.Enter(sponsorZone), "enter");
                Equal(true, h.Link.Last.ZoneTracking, "reported tracking");
                Equal("windy", h.Link.Last.ZoneType, "reported zone type");
            }),

            new TestCase("sponsor: switching back to our environments restores zone tracking", () =>
            {
                var h = new Harness();
                h.Environments.SetAvailable(EnvironmentId.Sponsor, true);
                h.Link.SimulateEnvironmentRequest("sponsor");
                h.ClearRecorded();

                h.Link.SimulateEnvironmentRequest("beach");
                Equal(EnvironmentId.Beach, h.Environments.Current, "environment");
                Equal(true, h.Zones.ZoneTrackingEnabled, "tracking");
                Equal(true, h.Link.Last.ZoneTracking, "reported tracking");
                Equal(ZoneInputResult.Changed, h.Zones.Enter(BeachSun), "beach zone");

                h.Link.SimulateEnvironmentRequest("sponsor");
                h.Link.SimulateEnvironmentRequest("forest");
                Equal(ZoneInputResult.Changed, h.Zones.Enter(ForestWind), "forest zone");
                Equal(5, h.Link.Published.Count, "messages: beach, beach zone, sponsor, forest, forest zone");
            }),

            new TestCase("sponsor: our three environments stay available and tracked", () =>
            {
                var h = new Harness();
                h.Environments.SetAvailable(EnvironmentId.Sponsor, true);
                foreach (var env in new[] { EnvironmentId.Beach, EnvironmentId.Forest, EnvironmentId.Desert })
                {
                    Equal(true, h.Environments.IsAvailable(env), $"{env} available");
                    Equal(true, h.Environments.HasZoneTracking(env), $"{env} tracked");
                }
                Equal(false, h.Environments.HasZoneTracking(EnvironmentId.Sponsor), "sponsor tracked by default");
                Equal(EnvironmentRequestResult.Invalid, h.Environments.Request("sponsors", "test"), "near-miss name");
            }),

            new TestCase("zones need an id and an environment", () =>
            {
                Throws<ArgumentException>(() => new ZoneDefinition("", ZoneType.Hot, EnvironmentId.Forest), "empty id");
                Throws<ArgumentException>(() => new ZoneDefinition("x", ZoneType.Hot, EnvironmentId.None), "no environment");
            }),
        };

        // ------------------------------------------------------ asserts
        static void Equal<T>(T expected, T actual, string what)
        {
            if (!EqualityComparer<T>.Default.Equals(expected, actual))
                throw new Exception($"{what}: expected {Show(expected)}, got {Show(actual)}");
        }

        static void Contains(string text, string part, string what)
        {
            if (!text.Contains(part)) throw new Exception($"{what}: '{part}' not found in {text}");
        }

        static void Throws<TException>(Action action, string what) where TException : Exception
        {
            try { action(); }
            catch (TException) { return; }
            throw new Exception($"{what}: expected {typeof(TException).Name}");
        }

        static string Show(object value) => value == null ? "null" : value.ToString();
    }
}
