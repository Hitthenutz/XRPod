import { useCallback, useEffect, useRef, useState } from "react";
import { getSettings, subscribe, updateSettings } from "@/api/pod";
import { SETTINGS_FIELDS } from "@/lib/podSettings";

// Changes made within this window are merged into one save, so tapping
// through scents or nudging a slider with the arrow keys costs one write.
const SAVE_DELAY_MS = 400;
// Backoff between retries when the Pi is busy, restarting or out of reach.
const RETRY_DELAYS_MS = [1000, 3000, 8000];

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Rate limits, server errors and dropped connections are worth retrying;
// anything else (bad data, permissions) will fail the same way again.
const isRetryable = (err) =>
  err?.status === undefined || err.status === 429 || err.status >= 500;

async function withRetry(fn) {
  for (let attempt = 0; ; attempt++) {
    try {
      return await fn();
    } catch (err) {
      if (attempt >= RETRY_DELAYS_MS.length || !isRetryable(err)) throw err;
      await sleep(RETRY_DELAYS_MS[attempt]);
    }
  }
}

/**
 * Loads the pod settings from the Pi and exposes `applyChanges(patch)`.
 *
 * Changes show up immediately (optimistic). After a short pause they are
 * merged into one write and retried if the Pi is briefly unreachable. The
 * Pi validates the change and logs one history row per changed field.
 *
 * `status` is "idle" | "saving" | "error".
 */
export function usePodSettings() {
  const [settings, setSettings] = useState(null);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState("idle");

  // What the user sees (optimistic) and what the server last confirmed.
  const settingsRef = useRef(null);
  const savedRef = useRef(null);
  // Fields changed since the last save started, and the debounce timer.
  const pendingRef = useRef({});
  const timerRef = useRef(null);
  // Saves run one at a time so they land in order.
  const queueRef = useRef(Promise.resolve());
  const inFlightRef = useRef(0);
  const lastErrorRef = useRef(null);

  const show = useCallback((next) => {
    settingsRef.current = next;
    setSettings(next);
  }, []);

  // Server state plus any local changes that haven't been saved yet.
  const showSavedWithPending = useCallback(() => {
    show({ ...savedRef.current, ...pendingRef.current });
  }, [show]);

  // After the last save in a row finishes, resync the screen with the
  // server (this also rolls back a failed save) while keeping any changes
  // the user made in the meantime, and report how it went.
  const settle = useCallback(() => {
    if (inFlightRef.current > 0 || timerRef.current) return;
    showSavedWithPending();
    setStatus(lastErrorRef.current ? "error" : "idle");
  }, [showSavedWithPending]);

  const save = useCallback(async (patch) => {
    // Snapshot now: the old values must not change under us while we await.
    const before = { ...savedRef.current };
    // Diff against the server, so A→B→A within one batch saves nothing.
    const changed = SETTINGS_FIELDS.filter(
      (f) => f in patch && patch[f] !== before[f],
    );
    if (changed.length === 0) return;

    const diff = Object.fromEntries(changed.map((f) => [f, patch[f]]));
    // The Pi returns the full saved settings (it may also have switched the
    // heater or AC off to keep them exclusive).
    savedRef.current = await withRetry(() => updateSettings(diff));
  }, []);

  const flush = useCallback(() => {
    timerRef.current = null;
    const patch = pendingRef.current;
    pendingRef.current = {};
    inFlightRef.current += 1;

    queueRef.current = queueRef.current.then(async () => {
      try {
        await save(patch);
        lastErrorRef.current = null;
        setError(null);
      } catch (err) {
        console.error("Failed to save settings:", err);
        lastErrorRef.current = err;
        setError(err);
      } finally {
        inFlightRef.current -= 1;
        settle();
      }
    });
  }, [save, settle]);

  useEffect(() => {
    let cancelled = false;

    const load = () =>
      withRetry(getSettings)
        .then((record) => {
          // Don't let a refetch clobber a save that's still in progress.
          if (cancelled || inFlightRef.current > 0) return;
          savedRef.current = record;
          showSavedWithPending();
          // Reachable again and showing the Pi's real values: clear errors.
          lastErrorRef.current = null;
          setError(null);
          setStatus((s) => (s === "error" ? "idle" : s));
        })
        .catch((err) => {
          if (cancelled) return;
          lastErrorRef.current = err;
          setError(err);
          setStatus("error");
        });

    load();

    // Changes made from another phone/tablet/laptop show up live, and a
    // reconnect after the Pi restarts or Wi-Fi drops reloads everything.
    // Local changes that haven't been saved yet stay on top.
    const unsubscribe = subscribe({
      settings: (record) => {
        savedRef.current = record;
        if (inFlightRef.current === 0) showSavedWithPending();
      },
      open: load,
    });

    return () => {
      cancelled = true;
      unsubscribe();
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [showSavedWithPending]);

  const applyChanges = useCallback(
    (patch) => {
      const current = settingsRef.current;
      if (!current) return;

      const changed = SETTINGS_FIELDS.filter(
        (f) => f in patch && patch[f] !== current[f],
      );
      if (changed.length === 0) return;

      const diff = Object.fromEntries(changed.map((f) => [f, patch[f]]));
      show({ ...current, ...diff });
      Object.assign(pendingRef.current, diff);
      setStatus("saving");

      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(flush, SAVE_DELAY_MS);
    },
    [show, flush],
  );

  return { settings, applyChanges, error, status };
}
