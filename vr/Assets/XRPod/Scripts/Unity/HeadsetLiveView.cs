// Sends the HUD a small picture of what the user sees, a few times a second
// (PUT {pod}/api/vr/frame, see docs/subsystems.md). HttpPodLink adds this by
// itself (its Send Live View box); nothing to set up in a scene.
//
// How: a second, low-resolution camera copies the head's position and
// direction, renders one frame into a texture now and then, and the picture
// is read back from the GPU without waiting for it, turned into a JPEG on a
// background thread and sent. It only runs while connected to the Pi, and
// skips a picture while the previous one is still on its way, so a slow
// Wi-Fi never piles up requests. Like everything here it only reports: the
// Pi keeps the newest picture in memory and never stores it.
//
// Cost on the headset: one extra 512 x 288 render about 8 times a second,
// without shadows or post-processing. Lower Frames Per Second or the size if
// a world gets choppy; untick Send Live View on HttpPodLink to turn it off.

using System;
using System.Collections;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.Experimental.Rendering;
using UnityEngine.Networking;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace XRPod.VR
{
    [RequireComponent(typeof(HttpPodLink))]
    public sealed class HeadsetLiveView : MonoBehaviour
    {
        // 8 smaller pictures a second cost the headset about the same as 4
        // bigger ones did (fewer pixels each), but look much smoother.
        [SerializeField] int width = 512;
        [SerializeField] int height = 288;
        [Tooltip("Pictures per second sent to the HUD.")]
        [SerializeField, Range(1f, 15f)] float framesPerSecond = 8f;
        [SerializeField, Range(20, 90)] int jpegQuality = 45;
        [Tooltip("Vertical field of view of the picture, in degrees.")]
        [SerializeField] float fieldOfView = 75f;
        [Tooltip("Tick if the picture shows upside down in the HUD.")]
        [SerializeField] bool flipVertically;

        HttpPodLink _link;
        Camera _eye;
        RenderTexture _target;
        string _ready;          // base64 JPEG waiting to be sent (set from a worker thread)
        int _working;           // 1 while a picture is being read back or encoded
        bool _sending;
        float _pausedUntil;     // after the Pi said it has no live view
        bool _warnedOldPi;

        void Awake()
        {
            _link = GetComponent<HttpPodLink>();
            _target = new RenderTexture(width, height, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB)
            {
                name = "XRPod live view",
            };
            _target.Create();

            _eye = new GameObject("Live view camera").AddComponent<Camera>();
            _eye.transform.SetParent(transform, false);
            _eye.enabled = false; // turned on for one frame per picture
            _eye.targetTexture = _target;
            _eye.stereoTargetEye = StereoTargetEyeMask.None;
            _eye.fieldOfView = fieldOfView;
            var data = _eye.GetUniversalAdditionalCameraData();
            data.allowXRRendering = false;
            data.renderShadows = false;
            data.renderPostProcessing = false;
            data.antialiasing = AntialiasingMode.None;
            data.requiresDepthTexture = false;
            data.requiresColorTexture = false;
        }

        void OnEnable() => StartCoroutine(Capture());

        // A finished picture goes out straight away (not on the next tick).
        void Update()
        {
            if (_ready != null && !_sending) StartCoroutine(Send(Interlocked.Exchange(ref _ready, null)));
        }

        void OnDestroy()
        {
            if (_target != null) _target.Release();
        }

        IEnumerator Capture()
        {
            var wait = new WaitForSecondsRealtime(1f / framesPerSecond);
            var endOfFrame = new WaitForEndOfFrame();
            while (true)
            {
                yield return wait;
                if (_link.Status != PodLinkStatus.Connected || Time.realtimeSinceStartup < _pausedUntil) continue;
                // The next picture can be made while the last one is still
                // on its way; only the newest one waiting is ever sent.
                if (Interlocked.CompareExchange(ref _working, 1, 0) != 0) continue;

                var head = Camera.main;
                if (head == null || head == _eye)
                {
                    _working = 0;
                    continue;
                }
                // Same place, direction and view as the user's eyes.
                _eye.transform.SetPositionAndRotation(head.transform.position, head.transform.rotation);
                _eye.cullingMask = head.cullingMask;
                _eye.clearFlags = head.clearFlags;
                _eye.backgroundColor = head.backgroundColor;
                _eye.nearClipPlane = head.nearClipPlane;
                _eye.farClipPlane = head.farClipPlane;
                _eye.enabled = true;
                yield return endOfFrame; // rendered this frame
                _eye.enabled = false;
                AsyncGPUReadback.Request(_target, 0, TextureFormat.RGBA32, OnReadback);
            }
        }

        // On the main thread, once the GPU has the picture ready.
        void OnReadback(AsyncGPUReadbackRequest request)
        {
            if (request.hasError || this == null)
            {
                _working = 0;
                return;
            }
            var pixels = request.GetData<byte>().ToArray();
            int w = width, h = height, quality = jpegQuality;
            var flip = flipVertically;
            Task.Run(() =>
            {
                try
                {
                    if (flip) FlipRows(pixels, w * 4, h);
                    var jpeg = ImageConversion.EncodeArrayToJPG(pixels, GraphicsFormat.R8G8B8A8_SRGB, (uint)w, (uint)h, 0, quality);
                    _ready = Convert.ToBase64String(jpeg);
                }
                catch (Exception err)
                {
                    Debug.LogWarning($"[XRPod] Live view picture failed: {err.Message}");
                }
                finally
                {
                    _working = 0;
                }
            });
        }

        static void FlipRows(byte[] pixels, int rowBytes, int rows)
        {
            var row = new byte[rowBytes];
            for (int top = 0, bottom = rows - 1; top < bottom; top++, bottom--)
            {
                Buffer.BlockCopy(pixels, top * rowBytes, row, 0, rowBytes);
                Buffer.BlockCopy(pixels, bottom * rowBytes, pixels, top * rowBytes, rowBytes);
                Buffer.BlockCopy(row, 0, pixels, bottom * rowBytes, rowBytes);
            }
        }

        IEnumerator Send(string jpegBase64)
        {
            _sending = true;
            var body = System.Text.Encoding.ASCII.GetBytes("{\"jpeg_base64\":\"" + jpegBase64 + "\"}");
            using (var request = new UnityWebRequest(_link.CurrentUrl + "/api/vr/frame", "PUT"))
            {
                request.uploadHandler = new UploadHandlerRaw(body);
                request.downloadHandler = new DownloadHandlerBuffer();
                request.SetRequestHeader("Content-Type", "application/json");
                request.timeout = 2;
                yield return request.SendWebRequest();

                if (request.responseCode == 404 || request.responseCode == 405)
                {
                    // The Pi's code is older than the live view: try again in a minute.
                    _pausedUntil = Time.realtimeSinceStartup + 60f;
                    if (!_warnedOldPi)
                    {
                        _warnedOldPi = true;
                        Debug.LogWarning($"[XRPod] {_link.CurrentUrl} has no live view (/api/vr/frame). Update the Pi's code to show the headset view in the HUD.", this);
                    }
                }
                else if (request.result == UnityWebRequest.Result.ProtocolError)
                {
                    Debug.LogWarning($"[XRPod] Pi rejected the live view picture ({request.responseCode}): {request.downloadHandler.text}", this);
                }
            }
            _sending = false;
        }
    }
}
