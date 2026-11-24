// Client for the API served by the Pi (pi/web.py). The HUD is served
// from the same Pi, so every path is relative; in development Vite proxies
// api to the Pi (see vite.config.js).
async function request(path, options = {}) {
  const res = await fetch(`/api${path}`, {
    ...options,
    headers: { Accept: "application/json", ...options.headers },
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const err = new Error(body?.error ?? `Pod server error (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return body;
}

export const getSettings = () => request("/settings");

export const updateSettings = (patch) =>
  request("/settings", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });

export const getLatestReading = () => request("/readings/latest");

export const getHistory = (limit = 50) => request(`/history?limit=${limit}`);

// what the headset last reported (via the Pi) or null if it hasn't reported yet
export const getVrState = () => request("/vr/state");

// The headset's newest live-view picture as a Blob (a JPEG), or null when
// there's none from the last few seconds (the Pi answers 204).
export async function getVrFrame(signal) {
  const res = await fetch("/api/vr/frame", { cache: "no-store", signal });
  if (res.status === 204) return null;
  if (!res.ok) throw new Error(`Pod server error (${res.status})`);
  return res.blob();
}

// ---- data log (pi/datalog.py) ----
// Events (node offline, sensor stopped, faults...), newest first. level
// "warning" leaves out info.
export const getLogEvents = (limit = 100, level = "info") =>
  request(`/log/events?limit=${limit}&level=${level}`);

// Recording sessions, newest first; the one recording has recording: true.
export const getSessions = () => request("/log/sessions");

// {action: "start", name} | {action: "stop"} | {action: "delete", id}
export const changeSession = (body) =>
  request("/log/session", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

// Link to a CSV download: kind "readings" or "events", for {session: id} or
// {minutes: n}.
export function logCsvUrl(kind, { session, minutes } = {}) {
  const query = session != null ? `session=${encodeURIComponent(session)}` : `minutes=${minutes ?? 60}`;
  return `/api/log/${kind}.csv?${query}`;
}

// One shared live connection for the whole HUD. EventSource reconnects by
// itself; `onOpen` fires on every (re)connect so callers can refetch anything
// they missed while offline.
const listeners = new Set();
let source = null;

function connect() {
  source = new EventSource("/api/events");
  for (const type of ["settings", "reading", "history", "vr", "event", "session", "ai"]) {
    source.addEventListener(type, (e) => {
      const data = JSON.parse(e.data);
      for (const l of listeners) l[type]?.(data);
    });
  }
  source.addEventListener("open", () => {
    for (const l of listeners) l.open?.();
  });
}

/**
 * Subscribe to live events: `{ settings(s), reading(r), history(rows), vr(state),
 * event(e), session(sessions), open() }`.
 * Returns an unsubscribe function.
 */
export function subscribe(handlers) {
  listeners.add(handlers);
  if (!source) connect();
  return () => {
    listeners.delete(handlers);
    if (listeners.size === 0 && source) {
      source.close();
      source = null;
    }
  };
}
