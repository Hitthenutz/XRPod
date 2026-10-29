// DRAFT: talks to the Pi over HTTP (which runs over TCP). The Pi doesn't
// support this yet. It uses the endpoints proposed in
// unity/docs/POD_PROTOCOL_PROPOSAL.md, which the Pi team still has to
// agree on and build. Until then:
//   - reading the selection does nothing (GET /api/settings exists, but
//     it has no selected_environment field yet),
//   - sending state gets a 404 or 405 (PUT /api/vr/state doesn't exist),
//     logged once.
// Leave VrSystemRoot's Pod Link empty to run offline instead.
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
        [Tooltip("The Pi's address. The Pi's IP (e.g. http://192.168.1.50) is more reliable on Quest than xrpod.local.")]
        [SerializeField] string baseUrl = "http://xrpod.local";
        [SerializeField] float pollSeconds = 1f;
        [SerializeField] float resendSeconds = 5f;
        [SerializeField] int timeoutSeconds = 3;

        public event Action<string> EnvironmentRequested;

        PodStateMessage _latest;
        bool _dirty;
        float _lastSentTime = float.NegativeInfinity;
        string _lastSelection;
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
            // React only to changes, so selecting an environment in the
            // Editor isn't undone by the next poll.
            if (string.IsNullOrEmpty(selection) || selection == _lastSelection) return;
            _lastSelection = selection;
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
                            Debug.LogWarning("[XRPod] The Pi has no /api/vr/state endpoint yet (see unity/docs/POD_PROTOCOL_PROPOSAL.md).", this);
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
