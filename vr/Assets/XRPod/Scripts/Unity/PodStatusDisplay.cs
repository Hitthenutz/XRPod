// A small line of text low in the user's view saying whether the headset is
// talking to the pod, e.g. "Looking for the pod on this Wi-Fi...". It hides
// a few seconds after connecting, so it's only there when something's off.
// HttpPodLink creates it; nothing to set up in a scene.

using UnityEngine;
using UnityEngine.UI;

namespace XRPod.VR
{
    public sealed class PodStatusDisplay : MonoBehaviour
    {
        const float ShowConnectedSeconds = 3f;

        HttpPodLink _link;
        Canvas _canvas;
        Text _text;
        PodLinkStatus _shown = (PodLinkStatus)(-1);
        float _connectedAt;

        public static PodStatusDisplay Create(HttpPodLink link)
        {
            var display = new GameObject("Pod status", typeof(RectTransform)).AddComponent<PodStatusDisplay>();
            display.transform.SetParent(link.transform, false);
            display._link = link;

            display._canvas = display.gameObject.AddComponent<Canvas>();
            display._canvas.renderMode = RenderMode.WorldSpace;
            display._canvas.sortingOrder = short.MaxValue - 1; // just under the fader
            var rect = (RectTransform)display.transform;
            rect.sizeDelta = new Vector2(900f, 90f);
            rect.localScale = Vector3.one * 0.0006f; // 900 units = 54 cm wide

            var panel = new GameObject("Panel", typeof(RectTransform)).AddComponent<Image>();
            panel.transform.SetParent(display.transform, false);
            panel.color = new Color(0f, 0f, 0f, 0.55f);
            panel.raycastTarget = false;
            panel.rectTransform.anchorMin = Vector2.zero;
            panel.rectTransform.anchorMax = Vector2.one;
            panel.rectTransform.offsetMin = Vector2.zero;
            panel.rectTransform.offsetMax = Vector2.zero;

            display._text = new GameObject("Text", typeof(RectTransform)).AddComponent<Text>();
            display._text.transform.SetParent(display.transform, false);
            display._text.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            display._text.fontSize = 40;
            display._text.alignment = TextAnchor.MiddleCenter;
            display._text.color = Color.white;
            display._text.raycastTarget = false;
            display._text.rectTransform.anchorMin = Vector2.zero;
            display._text.rectTransform.anchorMax = Vector2.one;
            display._text.rectTransform.offsetMin = Vector2.zero;
            display._text.rectTransform.offsetMax = Vector2.zero;
            return display;
        }

        void LateUpdate()
        {
            FollowHead();

            var status = _link.Status;
            if (status != _shown)
            {
                _shown = status;
                if (status == PodLinkStatus.Connected) _connectedAt = Time.unscaledTime;
                _text.text = Message(status);
            }
            _canvas.enabled = status != PodLinkStatus.Connected
                              || Time.unscaledTime - _connectedAt < ShowConnectedSeconds;
        }

        static string Message(PodLinkStatus status)
        {
            switch (status)
            {
                case PodLinkStatus.Connected: return "Connected to the pod";
                case PodLinkStatus.Searching: return "Looking for the pod on this Wi-Fi...";
                case PodLinkStatus.NotFound: return "Can't find the pod. Is the headset on the pod's Wi-Fi?";
                default: return "Connecting to the pod...";
            }
        }

        // Low in front of the user's eyes, upright, so it doesn't block the
        // view. Follows whichever camera is the main one (the XR rig's on the
        // headset).
        void FollowHead()
        {
            var head = Camera.main != null ? Camera.main.transform : null;
            if (head == null) return;
            var forward = Vector3.ProjectOnPlane(head.forward, Vector3.up);
            if (forward.sqrMagnitude < 0.01f) forward = head.up; // looking straight up or down
            forward.Normalize();
            transform.position = head.position + forward * 0.9f + Vector3.down * 0.35f;
            transform.rotation = Quaternion.LookRotation(forward, Vector3.up);
        }
    }
}
