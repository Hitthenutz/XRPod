// Gently bobs an object up and down and turns it, e.g. the floating shapes
// in the waiting room. Purely decoration.

using UnityEngine;

namespace XRPod.VR
{
    public sealed class FloatAndSpin : MonoBehaviour
    {
        [SerializeField] float bobMetres = 0.15f;
        [SerializeField] float bobSeconds = 4f;
        [SerializeField] float spinDegreesPerSecond = 15f;

        Vector3 _start;
        float _phase;

        void Start()
        {
            _start = transform.localPosition;
            // Different start points so the shapes don't move in step.
            _phase = (_start.x * 0.37f + _start.z * 0.61f) % 1f;
        }

        void Update()
        {
            var t = Time.time / bobSeconds + _phase;
            transform.localPosition = _start + Vector3.up * (Mathf.Sin(t * 2f * Mathf.PI) * bobMetres);
            transform.Rotate(0f, spinDegreesPerSecond * Time.deltaTime, 0f, Space.World);
        }
    }
}
