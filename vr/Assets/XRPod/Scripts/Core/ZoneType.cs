// A rough hint of what an area of a scene feels like. The zone's id is what
// counts: the Pi looks up each zone's recipe (temperature, fan, humidity,
// scent) by id, see vr/docs/ZONES.md. Unity only reports; the Pi decides
// what (if anything) to do.

namespace XRPod.VR.Core
{
    public enum ZoneType
    {
        Neutral = 0,
        Hot = 1,
        Cool = 2,
        Windy = 3,
    }

    public static class ZoneTypes
    {
        public static string ToWireName(ZoneType type)
        {
            switch (type)
            {
                case ZoneType.Hot: return "hot";
                case ZoneType.Cool: return "cool";
                case ZoneType.Windy: return "windy";
                default: return "neutral";
            }
        }
    }
}
