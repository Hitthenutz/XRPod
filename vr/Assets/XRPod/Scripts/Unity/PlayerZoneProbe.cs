// Marks the player's body for zone detection. Add it to a child of the
// XR Origin's Main Camera so it follows the user's head.
//
// Only this collider counts, not hands or controllers, so one person
// produces exactly one enter and one exit per zone.
//
// Unity only reports trigger contacts when one side has a Rigidbody, so
// this adds a kinematic one (it never moves the player or falls).

using UnityEngine;

namespace XRPod.VR
{
    [RequireComponent(typeof(SphereCollider), typeof(Rigidbody))]
    public sealed class PlayerZoneProbe : MonoBehaviour
    {
        // Runs when the component is first added in the Editor.
        void Reset()
        {
            var sphere = GetComponent<SphereCollider>();
            sphere.isTrigger = true;
            sphere.radius = 0.15f;
            Configure();
        }

        void Awake()
        {
            Configure();
            if (FindObjectsByType<PlayerZoneProbe>(FindObjectsSortMode.None).Length > 1)
                Debug.LogWarning("More than one PlayerZoneProbe: zones may see the player twice. Keep one.", this);
        }

        void Configure()
        {
            var body = GetComponent<Rigidbody>();
            body.isKinematic = true;
            body.useGravity = false;
        }
    }
}
