import { useEffect, useState } from "react";
import { getLatestReading, subscribe } from "@/api/pod";

const newer = (a, b) => !b || Number(a.id) >= Number(b.id);

/** The most recent sensor reading from the Pi, kept live. */
export function useLatestReading() {
  const [reading, setReading] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const keepNewest = (incoming) =>
      incoming && setReading((prev) => (newer(incoming, prev) ? incoming : prev));

    const load = () =>
      getLatestReading()
        .then((latest) => !cancelled && keepNewest(latest))
        .catch((err) => console.error("Failed to load sensor reading:", err))
        .finally(() => !cancelled && setLoading(false));

    load();
    const unsubscribe = subscribe({ reading: keepNewest, open: load });

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, []);

  return { reading, loading };
}
