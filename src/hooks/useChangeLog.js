import { useEffect, useState } from "react";
import { base44 } from "@/api/base44Client";
import { safeSubscribe } from "@/lib/subscribe";

const SettingsChangeLog = base44.entities.SettingsChangeLog;

// Unparseable dates sort last instead of scrambling the order.
const time = (e) => {
  const t = new Date(e.created_date).getTime();
  return Number.isFinite(t) ? t : -Infinity;
};

/** The most recent `limit` SettingsChangeLog entries, newest first, live. */
export function useChangeLog(limit = 50) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    // Merge by id and keep newest-first, so a live event that races the
    // initial fetch is neither lost nor duplicated.
    const merge = (incoming) =>
      setEntries((prev) => {
        const byId = new Map(prev.map((e) => [e.id, e]));
        for (const e of incoming) if (e?.id) byId.set(e.id, e);
        return [...byId.values()].sort((a, b) => time(b) - time(a)).slice(0, limit);
      });

    SettingsChangeLog.list("-created_date", limit)
      .then((rows) => !cancelled && merge(Array.isArray(rows) ? rows : []))
      .catch((err) => {
        console.error("Failed to load change history:", err);
        if (!cancelled) setError(err);
      })
      .finally(() => !cancelled && setLoading(false));

    const unsubscribe = safeSubscribe(
      SettingsChangeLog,
      (event) => {
        if (event?.type === "create" && event.data) {
          merge([{ id: event.id, created_date: event.timestamp, ...event.data }]);
        } else if (event?.type === "delete") {
          setEntries((prev) => prev.filter((e) => e.id !== event.id));
        }
      },
      "SettingsChangeLog",
    );

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [limit]);

  return { entries, loading, error };
}
