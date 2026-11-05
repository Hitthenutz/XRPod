// Walk around in the Editor without a headset. Put it on the player rig in
// the Bootstrap scene; it does nothing while a headset is in use (the
// headset moves the camera then).
//
//   W A S D            walk
//   hold right mouse   look around
//   Shift              walk faster

using UnityEngine;
using UnityEngine.XR;
#if ENABLE_INPUT_SYSTEM
using UnityEngine.InputSystem;
#endif

namespace XRPod.VR
{
    public sealed class DesktopTestMover : MonoBehaviour
    {
        [Tooltip("The camera, tilted up and down. The rig itself turns left and right.")]
        [SerializeField] Transform head;
        [SerializeField] float walkSpeed = 2f;
        [SerializeField] float runSpeed = 5f;
        [Tooltip("Degrees per pixel of mouse movement.")]
        [SerializeField] float lookSpeed = 0.15f;

        float _pitch;

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
            transform.position += move * (speed * Time.deltaTime);
#endif
        }
    }
}
