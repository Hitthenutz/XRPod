import { useEffect, useState } from "react";
import { getHistory, subscribe } from "@/api/pod";

/** The most recent `limit` settings changes, newest first, live. */
export function useChangeLog(limit = 50) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    // Merge by id and keep newest-first, so a live event that races a fetch
    // is neither lost nor duplicated. Ids increase, so they sort reliably
    // even when several rows share one timestamp.
    const merge = (incoming) =>
      setEntries((prev) => {
        const byId = new Map(prev.map((e) => [e.id, e]));
        for (const e of incoming) byId.set(e.id, e);
        return [...byId.values()]
          .sort((a, b) => Number(b.id) - Number(a.id))
          .slice(0, limit);
      });

    const load = () =>
      getHistory(limit)
        .then((rows) => !cancelled && merge(rows))
        .catch((err) => console.error("Failed to load change history:", err))
        .finally(() => !cancelled && setLoading(false));

    load();
    const unsubscribe = subscribe({
      history: (rows) => merge(rows),
      open: load, // catch up on anything missed while disconnected
    });

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [limit]);

  return { entries, loading };
}
