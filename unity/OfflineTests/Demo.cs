// A narrated walk through a session, printing every event and every message
// that would go to the Pi. Run with:
//   dotnet run --project unity/OfflineTests -- demo

using System;
using XRPod.VR.Core;

namespace XRPod.VR.OfflineTests
{
    static class Demo
    {
        public static void Run()
        {
            var link = new LoggingLink();
            var session = new VrSession(link, "demo");
            session.Zones.ActiveZoneChanged += e => Console.WriteLine($"    event: {e}");
            session.Environments.EnvironmentChanged += e => Console.WriteLine($"    event: {e}");
            session.Diagnostic += m => Console.WriteLine($"    warning: {m}");

            var wind = new ZoneDefinition("clearing-wind", ZoneType.Windy, EnvironmentId.Forest);
            var sun = new ZoneDefinition("sunny-patch", ZoneType.Hot, EnvironmentId.Forest);
            var dunes = new ZoneDefinition("hot-dunes", ZoneType.Hot, EnvironmentId.Desert);

            Step("App starts in the forest", () => session.Environments.Request(EnvironmentId.Forest, "startup"));
            Step("Walk into the windy clearing", () => session.Zones.Enter(wind));
            Step("Trigger fires again for the same zone (duplicate)", () => session.Zones.Enter(wind));
            Step("Step into a sunny patch inside the clearing (overlap)", () => session.Zones.Enter(sun));
            Step("Leave the sunny patch (back to the clearing)", () => session.Zones.Exit("sunny-patch"));
            Step("HUD selects the desert", () => link.Request("desert"));
            Step("Old forest trigger sends a late exit (ignored)", () => session.Zones.Exit("clearing-wind"));
            Step("Walk into the hot dunes", () => session.Zones.Enter(dunes));
            Step("HUD selects the desert again (ignored)", () => link.Request("desert"));
            Step("HUD sends a bad name (ignored)", () => link.Request("moon"));
            Step("Leave the dunes", () => session.Zones.Exit("hot-dunes"));
            Step("HUD selects the sponsor experience before it's integrated (ignored)", () => link.Request("sponsor"));
            Step("(Sponsor files integrated: mark it available, zone tracking still off)",
                () => session.Environments.SetAvailable(EnvironmentId.Sponsor, true));
            Step("HUD selects the sponsor experience", () => link.Request("sponsor"));
            Step("HUD selects the beach (back to our environments)", () => link.Request("beach"));
        }

        static void Step(string what, Action action)
        {
            Console.WriteLine($"> {what}");
            action();
        }

        sealed class LoggingLink : IPodLink
        {
            public event Action<string> EnvironmentRequested;
            public void PublishState(PodStateMessage state) => Console.WriteLine($"    to Pi: {state.ToJson()}");
            public void Request(string environment) => EnvironmentRequested?.Invoke(environment);
        }
    }
}
