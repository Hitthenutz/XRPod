// The virtual environments the pod can show. Each one is a Unity scene.
//
// Wire names ("beach", "forest", "desert", "sponsor") are what travels
// between Unity and the Pi, so they must match the Pi's list of allowed
// values.
//
// Sponsor is the experience our sponsor provides. It starts out
// unavailable, with zone tracking off, until their files are integrated
// (see EnvironmentController and unity/docs/SPONSOR_INTEGRATION.md).

namespace XRPod.VR.Core
{
    public enum EnvironmentId
    {
        None = 0, // nothing selected yet
        Beach = 1,
        Forest = 2,
        Desert = 3,
        Sponsor = 4,
    }

    public static class EnvironmentIds
    {
        public static readonly EnvironmentId[] All =
            { EnvironmentId.Beach, EnvironmentId.Forest, EnvironmentId.Desert, EnvironmentId.Sponsor };

        public static string ToWireName(EnvironmentId id)
        {
            switch (id)
            {
                case EnvironmentId.Beach: return "beach";
                case EnvironmentId.Forest: return "forest";
                case EnvironmentId.Desert: return "desert";
                case EnvironmentId.Sponsor: return "sponsor";
                default: return "none";
            }
        }

        // Accepts "forest", "Forest" or " forest ". Returns false for anything
        // unknown, including "none".
        public static bool TryParse(string name, out EnvironmentId id)
        {
            id = EnvironmentId.None;
            if (name == null) return false;
            foreach (var candidate in All)
            {
                if (ToWireName(candidate) == name.Trim().ToLowerInvariant())
                {
                    id = candidate;
                    return true;
                }
            }
            return false;
        }
    }
}
