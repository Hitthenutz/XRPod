import { useCallback, useEffect, useState } from "react";
import { changeSession, getLogEvents, getSessions, subscribe } from "@/api/pod";

const EVENT_LIMIT = 200;

/**
 * The data log, live: events (newest first), recording sessions, and
 * start / stop / delete for sessions. `error` is the last failed action.
 */
export function useDataLog() {
  const [events, setEvents] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    // Merge by id, newest first, so a live event racing a fetch is neither
    // lost nor duplicated.
    const merge = (incoming) =>
      setEvents((prev) => {
        const byId = new Map(prev.map((e) => [e.id, e]));
        for (const e of incoming) byId.set(e.id, e);
        return [...byId.values()].sort((a, b) => Number(b.id) - Number(a.id)).slice(0, EVENT_LIMIT);
      });

    const load = () =>
      Promise.all([getLogEvents(EVENT_LIMIT), getSessions()])
        .then(([rows, list]) => {
          if (cancelled) return;
          merge(rows);
          setSessions(list);
        })
        .catch((err) => console.error("Failed to load the data log:", err))
        .finally(() => !cancelled && setLoading(false));

    load();
    const unsubscribe = subscribe({
      event: (e) => merge([e]),
      session: (list) => setSessions(list),
      open: load, // catch up on anything missed while disconnected
    });
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, []);

  const act = useCallback(async (body) => {
    setError(null);
    try {
      const { sessions: list } = await changeSession(body);
      setSessions(list);
      return true;
    } catch (err) {
      setError(err);
      return false;
    }
  }, []);

  return {
    events,
    sessions,
    recording: sessions.find((s) => s.recording) ?? null,
    loading,
    error,
    start: (name) => act({ action: "start", name }),
    stop: () => act({ action: "stop" }),
    remove: (id) => act({ action: "delete", id }),
  };
}
