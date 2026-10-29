// The only thing the VR logic knows about the outside world.
//
// An implementation carries messages to and from the Pi however the team
// decides (HTTP polling today, maybe something else later). Swapping it
// doesn't touch zone detection or environment switching.
//
// Implementations must raise EnvironmentRequested on Unity's main thread.

using System;

namespace XRPod.VR.Core
{
    public interface IPodLink
    {
        // The pod asked for an environment, e.g. "forest" chosen in the HUD.
        // The name is passed through as-is; EnvironmentController rejects
        // unknown names.
        event Action<string> EnvironmentRequested;

        // Report what the VR user is seeing now. Only the newest state
        // matters, so an implementation may drop older ones it hasn't sent.
        void PublishState(PodStateMessage state);
    }
}
