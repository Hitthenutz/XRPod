// A pod link that goes nowhere: it keeps what was published and lets you
// pretend the pod asked for an environment. Used by the offline tests, and
// in Unity when no real link is set (no Pi needed).

using System;
using System.Collections.Generic;

namespace XRPod.VR.Core
{
    public sealed class InMemoryPodLink : IPodLink
    {
        public event Action<string> EnvironmentRequested;

        public List<PodStateMessage> Published { get; } = new List<PodStateMessage>();

        public PodStateMessage Last => Published.Count > 0 ? Published[Published.Count - 1] : null;

        public void PublishState(PodStateMessage state) => Published.Add(state);

        // Pretend the HUD selected an environment.
        public void SimulateEnvironmentRequest(string environment) => EnvironmentRequested?.Invoke(environment);
    }
}
