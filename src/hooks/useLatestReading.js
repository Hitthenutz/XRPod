import { useEffect, useState } from "react";
import { base44 } from "@/api/base44Client";

const SensorReading = base44.entities.SensorReading;

const newer = (a, b) =>
  !b || new Date(a.created_date).getTime() >= new Date(b.created_date).getTime();

/** The most recent SensorReading, kept live via subscribe(). */
export function useLatestReading() {
  const [reading, setReading] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    SensorReading.list("-created_date", 1)
      .then(([latest]) => {
        if (cancelled || !latest) return;
        setReading((prev) => (newer(latest, prev) ? latest : prev));
      })
      .catch((err) => console.error("Failed to load sensor reading:", err))
      .finally(() => !cancelled && setLoading(false));

    const unsubscribe = SensorReading.subscribe((event) => {
      if (event.type !== "create" || !event.data) return;
      const incoming = {
        id: event.id,
        created_date: event.timestamp,
        ...event.data,
      };
      setReading((prev) => (newer(incoming, prev) ? incoming : prev));
    });

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, []);

  return { reading, loading };
}
