// Talks to the Pi over HTTP (which runs over TCP), as described in
// vr/docs/POD_PROTOCOL_PROPOSAL.md. Add it to the XRPod object in Bootstrap
// and drag it onto VrSystemRoot's Pod Link; leave Pod Link empty to run
// offline instead (keyboard only).
//
// Base Url: http://localhost:8080 when the Pi software runs on this PC,
// otherwise the Pi's address on the pod's Wi-Fi (see UNITY_SETUP.md step 8).
// The Pi serves plain HTTP, so Player Settings > Allow downloads over HTTP
// must be Always allowed.
//
// This is the only file that knows about HTTP. A different transport
// (e.g. a raw TCP socket) would be another IPodLink class next to it.
//
//   Pi -> Unity: poll GET  {baseUrl}/api/settings, read selected_environment
//   Unity -> Pi: PUT        {baseUrl}/api/vr/state with a PodStateMessage
//
// Only the newest state is sent, and it's resent every few seconds so the
// Pi catches up after a restart. UnityWebRequest sends no Origin header,
// which the Pi's CSRF check allows for non-browser clients.

using System;
using System.Collections;
using UnityEngine;
using UnityEngine.Networking;
using XRPod.VR.Core;

namespace XRPod.VR
{
    public sealed class HttpPodLink : MonoBehaviour, IPodLink
    {
        [Tooltip("The Pi's address: http://localhost:8080 when the Pi software runs on this PC, or the Pi's IP on the pod's Wi-Fi " +
                 "(e.g. http://10.199.194.129 on Zainab's hotspot; check with hostname -I on the Pi). xrpod.local may not work on the Quest.")]
        [SerializeField] string baseUrl = "http://localhost:8080";
        [SerializeField] float pollSeconds = 1f;
        [SerializeField] float resendSeconds = 5f;
        [SerializeField] int timeoutSeconds = 3;

        public event Action<string> EnvironmentRequested;

        PodStateMessage _latest;
        bool _dirty;
        float _lastSentTime = float.NegativeInfinity;
        bool _warnedNoStateEndpoint;
        bool _warnedUnreachable;

        // Matches the part of GET /api/settings we read; JsonUtility skips
        // every other field.
        [Serializable]
        sealed class SettingsDto
        {
            public string selected_environment;
        }

        public void PublishState(PodStateMessage state)
        {
            _latest = state;
            _dirty = true;
        }

        void OnEnable()
        {
            StartCoroutine(PollSelection());
            StartCoroutine(SendState());
        }

        IEnumerator PollSelection()
        {
            var wait = new WaitForSeconds(pollSeconds);
            while (true)
            {
                using (var request = UnityWebRequest.Get(Url("/api/settings")))
                {
                    request.timeout = timeoutSeconds;
                    yield return request.SendWebRequest();

                    if (request.result == UnityWebRequest.Result.Success)
                    {
                        _warnedUnreachable = false;
                        HandleSettings(request.downloadHandler.text);
                    }
                    else if (!_warnedUnreachable)
                    {
                        _warnedUnreachable = true;
                        Debug.LogWarning($"[XRPod] Can't reach the Pi at {baseUrl}: {request.error}. Will keep trying.", this);
                    }
                }
                yield return wait;
            }
        }

        void HandleSettings(string json)
        {
            SettingsDto settings;
            try
            {
                settings = JsonUtility.FromJson<SettingsDto>(json);
            }
            catch (ArgumentException)
            {
                return;
            }
            var selection = settings?.selected_environment;
            // Pass on the HUD's choice every poll, not only when it changes,
            // so the headset always ends up where the HUD says, e.g. after a
            // restart. While connected the HUD is in charge: keyboard keys
            // in the Editor are undone by the next poll.
            if (string.IsNullOrEmpty(selection)) return;
            EnvironmentRequested?.Invoke(selection);
        }

        IEnumerator SendState()
        {
            while (true)
            {
                var due = _dirty || (_latest != null && Time.realtimeSinceStartup - _lastSentTime >= resendSeconds);
                if (!due)
                {
                    yield return null;
                    continue;
                }

                var state = _latest;
                _dirty = false;
                _lastSentTime = Time.realtimeSinceStartup;
                using (var request = new UnityWebRequest(Url("/api/vr/state"), "PUT"))
                {
                    request.uploadHandler = new UploadHandlerRaw(System.Text.Encoding.UTF8.GetBytes(state.ToJson()));
                    request.downloadHandler = new DownloadHandlerBuffer();
                    request.SetRequestHeader("Content-Type", "application/json");
                    request.timeout = timeoutSeconds;
                    yield return request.SendWebRequest();

                    if (request.responseCode == 404 || request.responseCode == 405)
                    {
                        if (!_warnedNoStateEndpoint)
                        {
                            _warnedNoStateEndpoint = true;
                            Debug.LogWarning($"[XRPod] {baseUrl} has no /api/vr/state. Is Base Url the Pi, and is its code up to date (main)?", this);
                        }
                    }
                    else if (request.result == UnityWebRequest.Result.ProtocolError)
                    {
                        Debug.LogWarning($"[XRPod] Pi rejected VR state ({request.responseCode}): {request.downloadHandler.text}", this);
                    }
                }
            }
        }

        string Url(string path) => baseUrl.TrimEnd('/') + path;
    }
}
