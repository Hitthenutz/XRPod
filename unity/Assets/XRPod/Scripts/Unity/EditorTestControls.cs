// Testing without the headset. Put it on any object in the Bootstrap scene.
//
//   1 / 2 / 3   switch to Beach / Forest / Desert
//   4           switch to the sponsor environment (if marked available)
//   P           pretend the pod asked for the next environment (only
//               when running offline, with no pod link set)
//
// It also shows the current environment and zone in the top-left corner of
// the Game view. The overlay isn't visible in the headset.
//
// To walk around in the Editor, use the XR Interaction Toolkit's
// XR Device Simulator (see unity/docs/UNITY_SETUP.md).

using UnityEngine;
using XRPod.VR.Core;
#if ENABLE_INPUT_SYSTEM
using UnityEngine.InputSystem;
#endif

namespace XRPod.VR
{
    public sealed class EditorTestControls : MonoBehaviour
    {
        [SerializeField] bool showOverlay = true;

        int _podRequestIndex;

        void Update()
        {
#if ENABLE_INPUT_SYSTEM
            var keyboard = Keyboard.current;
            var session = Session();
            if (keyboard == null || session == null) return;

            if (keyboard.digit1Key.wasPressedThisFrame) session.Environments.Request(EnvironmentId.Beach, "keyboard");
            if (keyboard.digit2Key.wasPressedThisFrame) session.Environments.Request(EnvironmentId.Forest, "keyboard");
            if (keyboard.digit3Key.wasPressedThisFrame) session.Environments.Request(EnvironmentId.Desert, "keyboard");
            if (keyboard.digit4Key.wasPressedThisFrame
                && session.Environments.Request(EnvironmentId.Sponsor, "keyboard") == EnvironmentRequestResult.Unavailable)
                Debug.Log("Sponsor environment isn't available yet (VrSystemRoot > Sponsor Available).");

            if (keyboard.pKey.wasPressedThisFrame)
            {
                var next = EnvironmentIds.All[_podRequestIndex++ % EnvironmentIds.All.Length];
                var link = FindPodLink();
                if (link != null) link.SimulateEnvironmentRequest(EnvironmentIds.ToWireName(next));
                else Debug.Log("P only works offline (VrSystemRoot has no pod link set).");
            }
#endif
        }

        void OnGUI()
        {
            var session = Session();
            if (!showOverlay || session == null) return;

            var zone = session.Zones.ActiveZone;
            var last = session.LastPublished;
            GUI.Label(new Rect(10, 10, 800, 80),
                $"Environment: {session.Environments.Current}\n" +
                $"Zone: {(!session.Zones.ZoneTrackingEnabled ? "tracking off" : zone == null ? "neutral" : zone.ToString())}" +
                $"   (inside {session.Zones.OccupiedCount})\n" +
                $"Last sent: {(last == null ? "-" : last.ToJson())}");
        }

        static VrSession Session() => VrSystemRoot.Instance != null ? VrSystemRoot.Instance.Session : null;

        // VrSystemRoot uses an InMemoryPodLink when no real link is set.
        static InMemoryPodLink FindPodLink() => VrSystemRoot.Instance != null ? VrSystemRoot.Instance.OfflineLink : null;
    }
}
