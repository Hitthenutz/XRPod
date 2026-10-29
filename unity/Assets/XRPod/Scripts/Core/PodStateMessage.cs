// What Unity reports to the Pi: the full current state, not just the change.
// If a message is lost, the next one still tells the Pi everything.
//
// Example:
//   {"session_id":"a1b2c3","seq":7,"environment":"forest",
//    "zone_id":"clearing-wind","zone_type":"windy","zone_tracking":true,
//    "reason":"zone_entered"}
//
// session_id is new each time the app starts and seq counts up within it,
// so the Pi can ignore a message older than one it has already seen.
//
// zone_tracking false (e.g. the sponsor's environment) means zones aren't
// detected there, so "neutral" means "unknown", not "no effect wanted".

using System.Globalization;
using System.Text;

namespace XRPod.VR.Core
{
    public sealed class PodStateMessage
    {
        public string SessionId;
        public long Seq;
        public string Environment; // "beach", "forest", "desert"
        public string ZoneId;      // null when neutral
        public string ZoneType;    // "neutral", "hot", "cool", "windy"
        public bool ZoneTracking;  // false: zones aren't detected in this environment
        public string Reason;      // "environment_changed", "zone_entered", "zone_exited"

        // Same place as `other`, ignoring the session, seq and reason.
        public bool SameStateAs(PodStateMessage other) =>
            other != null && Environment == other.Environment && ZoneId == other.ZoneId
            && ZoneType == other.ZoneType && ZoneTracking == other.ZoneTracking;

        // Hand-written so the Core code needs nothing from Unity.
        public string ToJson()
        {
            var sb = new StringBuilder("{");
            AppendField(sb, "session_id", SessionId);
            sb.Append(",\"seq\":").Append(Seq.ToString(CultureInfo.InvariantCulture));
            sb.Append(',');
            AppendField(sb, "environment", Environment);
            sb.Append(',');
            AppendField(sb, "zone_id", ZoneId);
            sb.Append(',');
            AppendField(sb, "zone_type", ZoneType);
            sb.Append(",\"zone_tracking\":").Append(ZoneTracking ? "true" : "false");
            sb.Append(',');
            AppendField(sb, "reason", Reason);
            return sb.Append('}').ToString();
        }

        public override string ToString() => ToJson();

        static void AppendField(StringBuilder sb, string name, string value)
        {
            sb.Append('"').Append(name).Append("\":");
            if (value == null)
            {
                sb.Append("null");
                return;
            }
            sb.Append('"');
            foreach (var c in value)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < ' ') sb.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                        else sb.Append(c);
                        break;
                }
            }
            sb.Append('"');
        }
    }
}
