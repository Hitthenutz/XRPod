// Fades the view to black and back, so a new environment doesn't pop in
// front of the user's eyes (uncomfortable in VR). EnvironmentSceneLoader
// creates one for itself; nothing to set up in a scene.
//
// It's a black UI canvas just in front of the main camera ("Screen Space -
// Camera"), which also renders in the headset, unlike an overlay canvas.

using System.Collections;
using UnityEngine;
using UnityEngine.UI;

namespace XRPod.VR
{
    public sealed class ScreenFader : MonoBehaviour
    {
        Canvas _canvas;
        CanvasGroup _group;

        public static ScreenFader Create(Transform parent)
        {
            var fader = new GameObject("Screen fader").AddComponent<ScreenFader>();
            fader.transform.SetParent(parent, false);

            fader._canvas = fader.gameObject.AddComponent<Canvas>();
            fader._canvas.renderMode = RenderMode.ScreenSpaceCamera;
            fader._canvas.planeDistance = 0.2f; // just past the camera's near clip
            fader._canvas.sortingOrder = short.MaxValue; // in front of any other UI

            fader._group = fader.gameObject.AddComponent<CanvasGroup>();
            fader._group.interactable = false;
            fader._group.blocksRaycasts = false;

            var black = new GameObject("Black").AddComponent<Image>();
            black.transform.SetParent(fader.transform, false);
            black.color = Color.black;
            black.raycastTarget = false;
            black.rectTransform.anchorMin = Vector2.zero;
            black.rectTransform.anchorMax = Vector2.one;
            black.rectTransform.offsetMin = Vector2.zero;
            black.rectTransform.offsetMax = Vector2.zero;

            fader.Alpha = 0f;
            return fader;
        }

        // 0 = clear, 1 = black.
        public float Alpha
        {
            get => _group.alpha;
            set
            {
                _group.alpha = value;
                _canvas.enabled = value > 0f;
                // The camera can change, e.g. when the XR Origin replaces the
                // desktop test player.
                if (_canvas.enabled && _canvas.worldCamera == null) _canvas.worldCamera = Camera.main;
            }
        }

        public IEnumerator FadeTo(float target, float seconds)
        {
            var start = Alpha;
            for (var t = 0f; t < seconds; t += Time.unscaledDeltaTime)
            {
                Alpha = Mathf.Lerp(start, target, t / seconds);
                yield return null;
            }
            Alpha = target;
        }
    }
}
