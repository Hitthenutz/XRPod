// Where the user starts when this environment loads. Put it on an empty
// object in the environment scene, on the floor, facing the way the user
// should look (its blue Z arrow). Use one per scene.
//
// Without one, the user starts at the scene's origin facing +Z.

using UnityEngine;

namespace XRPod.VR
{
    public sealed class EnvironmentSpawnPoint : MonoBehaviour
    {
        // Shows the spot in the Scene view: a disc where the user stands and
        // a line where they look.
        void OnDrawGizmos()
        {
            Gizmos.color = new Color(0.2f, 0.9f, 0.4f);
            Gizmos.DrawWireSphere(transform.position + Vector3.up * 0.05f, 0.4f);
            var eye = transform.position + Vector3.up * 1.6f;
            Gizmos.DrawLine(transform.position, eye);
            Gizmos.DrawLine(eye, eye + transform.forward * 1.5f);
        }
    }
}
