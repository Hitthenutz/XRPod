import { useEffect, useState } from "react";
import { base44 } from "@/api/base44Client";

const SettingsChangeLog = base44.entities.SettingsChangeLog;

/** The most recent `limit` SettingsChangeLog entries, newest first, live. */
export function useChangeLog(limit = 50) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    // Merge by id and keep newest-first, so a live event that races the
    // initial fetch is neither lost nor duplicated.
    const merge = (incoming) =>
      setEntries((prev) => {
        const byId = new Map(prev.map((e) => [e.id, e]));
        for (const e of incoming) byId.set(e.id, e);
        return [...byId.values()]
          .sort((a, b) => new Date(b.created_date) - new Date(a.created_date))
          .slice(0, limit);
      });

    SettingsChangeLog.list("-created_date", limit)
      .then((rows) => !cancelled && merge(rows))
      .catch((err) => console.error("Failed to load change history:", err))
      .finally(() => !cancelled && setLoading(false));

    const unsubscribe = SettingsChangeLog.subscribe((event) => {
      if (event.type === "create" && event.data) {
        merge([{ id: event.id, created_date: event.timestamp, ...event.data }]);
      } else if (event.type === "delete") {
        setEntries((prev) => prev.filter((e) => e.id !== event.id));
      }
    });

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [limit]);

  return { entries, loading };
}
