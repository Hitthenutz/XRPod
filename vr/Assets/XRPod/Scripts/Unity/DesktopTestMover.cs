// Walk around in the Editor without a headset. Put it on the player rig in
// the Bootstrap scene; it does nothing while a headset is in use (the
// headset moves the camera then).
//
//   W A S D            walk
//   hold right mouse   look around
//   Shift              walk faster
//
// The rig gets a body (a CharacterController) while walking this way, so it
// bumps into scenery that has colliders, walks up slopes and small steps,
// falls back to the ground, and stays out of deep water. Eyes are Eye Height
// above the feet.

using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.XR;
#if ENABLE_INPUT_SYSTEM
using UnityEngine.InputSystem;
#endif

namespace XRPod.VR
{
    public sealed class DesktopTestMover : MonoBehaviour
    {
        // How far the feet may go below the water's surface: wading, not
        // swimming.
        const float MaxWaterDepth = 0.4f;
        const float Gravity = -9.81f;

        [Tooltip("The camera, tilted up and down. The rig itself turns left and right.")]
        [SerializeField] Transform head;
        [SerializeField] float walkSpeed = 2f;
        [SerializeField] float runSpeed = 9f;
        [Tooltip("Degrees per pixel of mouse movement.")]
        [SerializeField] float lookSpeed = 0.15f;
        [Tooltip("How high the eyes are above the ground, in metres.")]
        [SerializeField] float eyeHeight = 1.6f;

        float _pitch;
        float _fallSpeed;
        readonly RaycastHit[] _below = new RaycastHit[16];
        CharacterController _body;
        Scene _waterScene;
        float? _waterLevel;

        // Eyes exactly Eye Height above the feet. Done every frame, after
        // everything else: on the VR rig the camera sits under a "Camera
        // Offset" that the XR Origin lifts by itself (1.36 m without a
        // headset), so setting the camera's own height once put the eyes
        // about 3 m up, above the beach umbrellas. With a headset on, the
        // headset decides the height and this does nothing.
        void LateUpdate()
        {
            if (head == null || XRSettings.isDeviceActive) return;
            var p = head.position;
            head.position = new Vector3(p.x, transform.position.y + eyeHeight, p.z);
        }

        // Bottom-left: what the feet are on and how high the eyes are above
        // it, to spot standing on something unexpected.
        void OnGUI()
        {
            if (head == null || XRSettings.isDeviceActive) return;
            // The nearest thing under the eyes that isn't our own body.
            var count = Physics.RaycastNonAlloc(head.position, Vector3.down, _below, 50f, ~0, QueryTriggerInteraction.Ignore);
            Collider ground = null;
            var groundY = 0f;
            for (var i = 0; i < count; i++)
            {
                var hit = _below[i];
                if (hit.collider.transform.IsChildOf(transform)) continue;
                if (ground != null && hit.point.y <= groundY) continue;
                ground = hit.collider;
                groundY = hit.point.y;
            }
            GUI.Label(new Rect(10, Screen.height - 30, 700, 24), ground != null
                ? $"Standing on: {ground.name}   eyes {head.position.y - groundY:0.00} m above it"
                : "Standing on: nothing");
        }

        // A body about as big as a person, only for walking with the keyboard.
        CharacterController Body()
        {
            if (_body != null) return _body;
            _body = GetComponent<CharacterController>();
            if (_body == null) _body = gameObject.AddComponent<CharacterController>();
            _body.height = eyeHeight + 0.15f;
            _body.radius = 0.25f;
            _body.center = new Vector3(0f, _body.height / 2f, 0f);
            _body.stepOffset = 0.35f; // step over toys, towels, kerbs
            _body.slopeLimit = 50f;
            _body.skinWidth = 0.03f;
            return _body;
        }

        void Update()
        {
#if ENABLE_INPUT_SYSTEM
            if (XRSettings.isDeviceActive) return;
            var keyboard = Keyboard.current;
            var mouse = Mouse.current;
            if (keyboard == null || mouse == null) return;

            if (mouse.rightButton.isPressed)
            {
                var delta = mouse.delta.ReadValue() * lookSpeed;
                transform.Rotate(0f, delta.x, 0f);
                _pitch = Mathf.Clamp(_pitch - delta.y, -80f, 80f);
                if (head != null) head.localEulerAngles = new Vector3(_pitch, 0f, 0f);
            }

            var input = Vector2.zero;
            if (keyboard.wKey.isPressed) input.y += 1f;
            if (keyboard.sKey.isPressed) input.y -= 1f;
            if (keyboard.dKey.isPressed) input.x += 1f;
            if (keyboard.aKey.isPressed) input.x -= 1f;

            // The rig only turns around Y, so forward stays level with the ground.
            var move = Vector3.ClampMagnitude(transform.forward * input.y + transform.right * input.x, 1f);
            var speed = keyboard.leftShiftKey.isPressed ? runSpeed : walkSpeed;

            var body = Body();
            _fallSpeed = body.isGrounded ? -1f : _fallSpeed + Gravity * Time.deltaTime;
            body.Move((move * speed + Vector3.up * _fallSpeed) * Time.deltaTime);

            // Wading, not swimming: never more than knee deep.
            var water = WaterLevel();
            if (water.HasValue && transform.position.y < water.Value - MaxWaterDepth)
            {
                body.Move(Vector3.up * (water.Value - MaxWaterDepth - transform.position.y));
                _fallSpeed = 0f;
            }
#endif
        }

        // The water surface in the world showing now (an object named water,
        // ocean or sea), looked up once per world. null if there's none.
        float? WaterLevel()
        {
            var scene = SceneManager.GetActiveScene();
            if (scene == _waterScene) return _waterLevel;
            _waterScene = scene;
            _waterLevel = null;
            foreach (var root in scene.GetRootGameObjects())
            foreach (var renderer in root.GetComponentsInChildren<Renderer>())
            {
                var name = renderer.name.ToLowerInvariant();
                if (name.Contains("water") || name.Contains("ocean") || name.Contains("sea"))
                {
                    _waterLevel = renderer.bounds.center.y;
                    return _waterLevel;
                }
            }
            return _waterLevel;
        }
    }
}
