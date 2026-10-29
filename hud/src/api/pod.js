// Client for the API served by the Pi (pi/web.py). The HUD is served
// from the same Pi, so every path is relative; in development Vite proxies
// /api to the Pi (see vite.config.js).

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

// One shared live connection for the whole HUD. EventSource reconnects by
// itself; `onOpen` fires on every (re)connect so callers can refetch anything
// they missed while offline.
const listeners = new Set();
let source = null;

function connect() {
  source = new EventSource("/api/events");
  for (const type of ["settings", "reading", "history"]) {
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
 * Subscribe to live events: `{ settings(s), reading(r), history(rows), open() }`.
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
