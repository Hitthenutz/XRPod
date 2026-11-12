// Talks to the Pi over HTTP (which runs over TCP), as described in
// vr/docs/POD_PROTOCOL_PROPOSAL.md. Add it to the XRPod object in Bootstrap
// and drag it onto VrSystemRoot's Pod Link; leave Pod Link empty to run
// offline instead (keyboard only).
//
// Base Url: http://localhost:8080 when the Pi software runs on this PC.
// On the headset it doesn't need to be right: if the Pi doesn't answer, the
// app looks for it on the headset's Wi-Fi (PodAddresses) and remembers the
// address that worked. The Pi serves plain HTTP, so Player Settings > Allow
// downloads over HTTP must be Always allowed.
//
// This is the only file that knows about HTTP. A different transport
// (e.g. a raw TCP socket) would be another IPodLink class next to it.
//
//   Pi -> Unity: poll GET  {url}/api/settings, read selected_environment
//   Unity -> Pi: PUT        {url}/api/vr/state with a PodStateMessage
//
// Only the newest state is sent, and it's resent every few seconds so the
// Pi catches up after a restart. UnityWebRequest sends no Origin header,
// which the Pi's CSRF check allows for non-browser clients.

using System;
using System.Collections;
using System.Collections.Generic;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using UnityEngine;
using UnityEngine.Networking;
using XRPod.VR.Core;

namespace XRPod.VR
{
    public enum PodLinkStatus
    {
        Connecting, // trying the current address
        Connected,  // the Pi answered recently
        Searching,  // looking for the Pi on the Wi-Fi
        NotFound,   // looked everywhere; trying again shortly
    }

    public sealed class HttpPodLink : MonoBehaviour, IPodLink
    {
        const string LastWorkingKey = "XRPod.PodUrl";

        [Tooltip("Where to look first: http://localhost:8080 when the Pi software runs on this PC, or the Pi's address " +
                 "(e.g. http://10.199.194.129). If it doesn't answer, the app searches the Wi-Fi (Auto Find).")]
        [SerializeField] string baseUrl = "http://localhost:8080";
        [Tooltip("Look for the Pi on the headset's Wi-Fi when the address above doesn't answer.")]
        [SerializeField] bool autoFind = true;
        [Tooltip("Show the connection status in front of the user (hidden while connected).")]
        [SerializeField] bool showStatus = true;
        [SerializeField] float pollSeconds = 1f;
        [SerializeField] float resendSeconds = 5f;
        [SerializeField] int timeoutSeconds = 3;

        public event Action<string> EnvironmentRequested;

        public PodLinkStatus Status { get; private set; } = PodLinkStatus.Connecting;

        // The address in use now (may differ from Base Url after a search).
        public string CurrentUrl { get; private set; }

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

        void Awake()
        {
            CurrentUrl = PodAddresses.Normalize(baseUrl);
            if (showStatus) PodStatusDisplay.Create(this);
        }

        void OnEnable()
        {
            StartCoroutine(PollSelection());
            StartCoroutine(SendState());
        }

        IEnumerator PollSelection()
        {
            var wait = new WaitForSecondsRealtime(pollSeconds);
            var failures = 0;
            while (true)
            {
                using (var request = UnityWebRequest.Get(Url("/api/settings")))
                {
                    request.timeout = timeoutSeconds;
                    yield return request.SendWebRequest();

                    if (request.result == UnityWebRequest.Result.Success)
                    {
                        failures = 0;
                        _warnedUnreachable = false;
                        if (Status != PodLinkStatus.Connected)
                        {
                            Debug.Log($"[XRPod] Connected to the pod at {CurrentUrl}.", this);
                            PlayerPrefs.SetString(LastWorkingKey, CurrentUrl);
                            PlayerPrefs.Save();
                        }
                        Status = PodLinkStatus.Connected;
                        HandleSettings(request.downloadHandler.text);
                    }
                    else
                    {
                        failures++;
                        if (Status == PodLinkStatus.Connected) Status = PodLinkStatus.Connecting;
                        if (!_warnedUnreachable)
                        {
                            _warnedUnreachable = true;
                            Debug.LogWarning($"[XRPod] Can't reach the pod at {CurrentUrl}: {request.error}. Will keep trying.", this);
                        }
                    }
                }

                // A few misses in a row (not one dropped request): go looking.
                if (failures >= 3 && autoFind)
                {
                    yield return FindPod();
                    failures = 0;
                }
                yield return wait;
            }
        }

        // Asks every candidate address at once, a batch at a time, and keeps
        // the first one whose server is the XRPod Pi.
        IEnumerator FindPod()
        {
            Status = PodLinkStatus.Searching;
            var candidates = PodAddresses.Candidates(baseUrl, PlayerPrefs.GetString(LastWorkingKey, ""), LocalIPv4());
            const int batchSize = 32;
            for (var start = 0; start < candidates.Count; start += batchSize)
            {
                var batch = new List<(string url, UnityWebRequest request)>();
                for (var i = start; i < Math.Min(start + batchSize, candidates.Count); i++)
                {
                    var probe = UnityWebRequest.Get(candidates[i] + "/api/vr/state");
                    probe.timeout = 2;
                    probe.SendWebRequest();
                    batch.Add((candidates[i], probe));
                }
                while (batch.Exists(b => !b.request.isDone)) yield return null;

                string found = null;
                foreach (var (url, request) in batch)
                {
                    if (found == null && request.result == UnityWebRequest.Result.Success
                        && PodAddresses.IsPodServer(request.GetResponseHeader("Server")))
                        found = url;
                    request.Dispose();
                }
                if (found != null)
                {
                    Debug.Log($"[XRPod] Found the pod at {found}.", this);
                    CurrentUrl = found;
                    _warnedUnreachable = false;
                    Status = PodLinkStatus.Connecting; // the next poll confirms it
                    yield break;
                }
            }

            Debug.LogWarning("[XRPod] Couldn't find the pod on this Wi-Fi. Is the headset on the pod's network? Trying again shortly.", this);
            Status = PodLinkStatus.NotFound;
            yield return new WaitForSecondsRealtime(5f);
        }

        // The headset's own address on the Wi-Fi, e.g. 10.199.194.57, or
        // null if it can't be found (then only the fixed addresses are tried).
        static string LocalIPv4()
        {
            try
            {
                foreach (var network in NetworkInterface.GetAllNetworkInterfaces())
                {
                    if (network.OperationalStatus != OperationalStatus.Up
                        || network.NetworkInterfaceType == NetworkInterfaceType.Loopback) continue;
                    foreach (var address in network.GetIPProperties().UnicastAddresses)
                        if (address.Address.AddressFamily == AddressFamily.InterNetwork)
                            return address.Address.ToString();
                }
            }
            catch (Exception)
            {
                // Some platforms don't list network interfaces; try DNS below.
            }
            try
            {
                foreach (var address in Dns.GetHostAddresses(Dns.GetHostName()))
                    if (address.AddressFamily == AddressFamily.InterNetwork && !IPAddress.IsLoopback(address))
                        return address.ToString();
            }
            catch (Exception)
            {
                // No address: only the fixed candidates are tried.
            }
            return null;
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
                            Debug.LogWarning($"[XRPod] {CurrentUrl} has no /api/vr/state. Is it the Pi, and is its code up to date (main)?", this);
                        }
                    }
                    else if (request.result == UnityWebRequest.Result.ProtocolError)
                    {
                        Debug.LogWarning($"[XRPod] Pi rejected VR state ({request.responseCode}): {request.downloadHandler.text}", this);
                    }
                }
            }
        }

        string Url(string path) => CurrentUrl + path;
    }
}
