// Menu XRPod > Measure Selected: shows how tall and wide the selected
// object is in metres (everything it draws, children included), next to
// the user's eye height, to check a store pack's props are real-world size.

using UnityEditor;
using UnityEngine;

namespace XRPod.VR
{
    static class XRPodMeasure
    {
        const float EyeHeight = 1.6f; // the desktop test player's camera height

        [MenuItem("XRPod/Measure Selected")]
        static void MeasureSelected()
        {
            var selected = Selection.activeGameObject;
            if (selected == null)
            {
                EditorUtility.DisplayDialog("XRPod", "Click an object first (in the Hierarchy or the Scene view).", "OK");
                return;
            }
            var renderers = selected.GetComponentsInChildren<Renderer>();
            if (renderers.Length == 0)
            {
                EditorUtility.DisplayDialog("XRPod", $"{selected.name} has nothing visible to measure.", "OK");
                return;
            }
            var bounds = renderers[0].bounds;
            foreach (var renderer in renderers) bounds.Encapsulate(renderer.bounds);
            var size = bounds.size;
            EditorUtility.DisplayDialog("XRPod",
                $"{selected.name}\n\nHeight: {size.y:0.00} m\nWidth: {size.x:0.00} m x {size.z:0.00} m\n\n" +
                $"For comparison: the test player's eyes are at {EyeHeight} m. A real beach umbrella " +
                "is about 2.2-2.5 m tall, a deck chair about 0.8-1 m.", "OK");
        }
    }
}
