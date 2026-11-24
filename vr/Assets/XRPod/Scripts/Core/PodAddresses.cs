// Where to look for the Pi when the headset can't reach it. On a phone
// hotspot the Pi's address can change, so instead of typing it into the
// headset, the app tries, in order:
//   1. the address set in Unity (HttpPodLink's Base Url),
//   2. the last address that worked on this headset,
//   3. the usual names: xrpod.local, and 10.42.0.1 (the Pi's own hotspot),
//   4. every other address on the headset's own Wi-Fi network (x.x.x.1-254).
// A reply only counts if the server calls itself XRPod (pi/web.py sets it),
// so another device that happens to answer isn't mistaken for the Pi.

using System;
using System.Collections.Generic;

namespace XRPod.VR.Core
{
    public static class PodAddresses
    {
        public static List<string> Candidates(string configured, string lastWorking, string localIPv4)
        {
            var list = new List<string>();
            void Add(string url)
            {
                url = Normalize(url);
                if (url != null && !list.Contains(url)) list.Add(url);
            }

            Add(configured);
            Add(lastWorking);
            Add("http://xrpod.local");
            Add("http://10.42.0.1");
            if (TryParseIPv4(localIPv4, out var ip))
            {
                for (var host = 1; host < 255; host++)
                    if (host != ip[3]) Add($"http://{ip[0]}.{ip[1]}.{ip[2]}.{host}");
            }
            return list;
        }

        // "10.199.194.129" -> "http://10.199.194.129"; trims spaces and a
        // trailing slash. null for an empty address.
        public static string Normalize(string url)
        {
            if (string.IsNullOrWhiteSpace(url)) return null;
            url = url.Trim().TrimEnd('/');
            return url.Contains("://") ? url : "http://" + url;
        }

        // The Pi answers with a Server header like "XRPod Python/3.12.10".
        public static bool IsPodServer(string serverHeader) =>
            serverHeader != null && serverHeader.StartsWith("XRPod", StringComparison.Ordinal);

        // Only a real network address: not loopback (127.x) or "no address"
        // (169.254.x, 0.x).
        static bool TryParseIPv4(string text, out int[] ip)
        {
            ip = new int[4];
            var parts = text?.Trim().Split('.');
            if (parts == null || parts.Length != 4) return false;
            for (var i = 0; i < 4; i++)
                if (!int.TryParse(parts[i], out ip[i]) || ip[i] < 0 || ip[i] > 255) return false;
            return ip[0] != 0 && ip[0] != 127 && !(ip[0] == 169 && ip[1] == 254);
        }
    }
}
