import { useCallback, useEffect, useRef, useState } from "react";
import { base44 } from "@/api/base44Client";
import {
  DEFAULT_SETTINGS,
  SETTINGS_FIELDS,
  stringifyValue,
} from "@/lib/podSettings";

const PodSettings = base44.entities.PodSettings;
const SettingsChangeLog = base44.entities.SettingsChangeLog;

// Changes made within this window are merged into one save, so tapping
// through scents or nudging a slider with the arrow keys costs one write.
const SAVE_DELAY_MS = 400;
// Backoff between retries when Base44 is busy (rate limit / 5xx / offline).
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

// The oldest PodSettings record is the canonical one (the Pi agent uses the
// same rule), so a duplicate created by a race is harmlessly ignored.
async function loadOrCreateSettings() {
  const [existing] = await PodSettings.list("created_date", 1);
  if (existing) return existing;
  return PodSettings.create(DEFAULT_SETTINGS);
}

async function currentUserEmail() {
  try {
    const user = await base44.auth.me();
    return user?.email ?? null;
  } catch {
    return null; // not logged in — fine, there's no auth yet
  }
}

/**
 * Loads the single PodSettings record and exposes `applyChanges(patch)`.
 *
 * Changes show up immediately (optimistic). After a short pause they are
 * merged into one write, retried if Base44 is busy, and logged as one
 * SettingsChangeLog row per field whose saved value actually changed.
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
  const emailRef = useRef(undefined);

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
    const saved = await withRetry(() => PodSettings.update(before.id, diff));
    savedRef.current = { ...before, ...diff, ...saved };

    const changed_by = emailRef.current ?? null;
    await withRetry(() =>
      SettingsChangeLog.bulkCreate(
        changed.map((f) => ({
          field_name: f,
          old_value: stringifyValue(before[f]),
          new_value: stringifyValue(patch[f]),
          changed_by,
        })),
      ),
    );
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
    withRetry(loadOrCreateSettings)
      .then((record) => {
        if (cancelled) return;
        savedRef.current = record;
        show(record);
      })
      .catch((err) => {
        if (cancelled) return;
        lastErrorRef.current = err;
        setError(err);
        setStatus("error");
      });

    currentUserEmail().then((email) => {
      emailRef.current = email;
    });

    // Changes made from another phone/tablet/laptop show up live. Local
    // changes that haven't been saved yet stay on top.
    const unsubscribe = PodSettings.subscribe((event) => {
      const saved = savedRef.current;
      if (!saved || event.id !== saved.id || event.type !== "update") return;
      savedRef.current = { ...saved, ...event.data };
      if (inFlightRef.current === 0) showSavedWithPending();
    });

    return () => {
      cancelled = true;
      unsubscribe();
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [show, showSavedWithPending]);

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
