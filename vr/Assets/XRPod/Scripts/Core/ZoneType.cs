// What kind of physical effect an area of a scene is meant to suggest.
// Unity only reports the type; the Pi decides what (if anything) to do.

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
