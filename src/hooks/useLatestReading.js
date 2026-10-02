import { useEffect, useState } from "react";
import { base44 } from "@/api/base44Client";
import { safeSubscribe } from "@/lib/subscribe";

const SensorReading = base44.entities.SensorReading;

const time = (r) => new Date(r?.created_date).getTime();

// Readings with an unparseable date never replace a good one.
const newer = (a, b) => !b || !Number.isFinite(time(b)) || time(a) >= time(b);

/** The most recent SensorReading, kept live via subscribe(). */
export function useLatestReading() {
  const [reading, setReading] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    SensorReading.list("-created_date", 1)
      .then((rows) => {
        const latest = Array.isArray(rows) ? rows[0] : null;
        if (cancelled || !latest) return;
        setReading((prev) => (newer(latest, prev) ? latest : prev));
      })
      .catch((err) => {
        console.error("Failed to load sensor reading:", err);
        if (!cancelled) setError(err);
      })
      .finally(() => !cancelled && setLoading(false));

    const unsubscribe = safeSubscribe(
      SensorReading,
      (event) => {
        if (event?.type !== "create" || !event.data) return;
        const incoming = {
          id: event.id,
          created_date: event.timestamp,
          ...event.data,
        };
        setError(null);
        setReading((prev) => (newer(incoming, prev) ? incoming : prev));
      },
      "SensorReading",
    );

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, []);

  return { reading, loading, error };
}
