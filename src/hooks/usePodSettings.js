import { useCallback, useEffect, useRef, useState } from "react";
import { base44 } from "@/api/base44Client";
import {
  DEFAULT_SETTINGS,
  SETTINGS_FIELDS,
  stringifyValue,
} from "@/lib/podSettings";
import { safeSubscribe } from "@/lib/subscribe";

const PodSettings = base44.entities.PodSettings;
const SettingsChangeLog = base44.entities.SettingsChangeLog;

// Initial load retries with backoff: 2s, 4s, 8s … capped at 30s.
const RETRY_BASE_MS = 2000;
const RETRY_MAX_MS = 30000;

// The oldest PodSettings record is the canonical one (the Pi agent uses the
// same rule), so a duplicate created by a race is harmlessly ignored.
async function loadOrCreateSettings() {
  const rows = await PodSettings.list("created_date", 1);
  const existing = Array.isArray(rows) ? rows[0] : null;
  if (existing) return existing;
  return PodSettings.create(DEFAULT_SETTINGS);
}

// Fill in fields a record is missing (e.g. created before a field existed),
// so the controls never see undefined.
const withDefaults = (record) => ({ ...DEFAULT_SETTINGS, ...record });

const userError = (message, cause) =>
  new Error(`${message} ${cause?.message ?? String(cause ?? "")}`.trim(), { cause });

async function currentUserEmail() {
  try {
    const user = await base44.auth.me();
    return user?.email ?? null;
  } catch {
    return null; // not logged in — fine, there's no auth yet
  }
}

/**
 * Loads the single PodSettings record and exposes `applyChanges(patch)`,
 * which updates local state immediately (optimistic), writes the patch to
 * the record, and logs one SettingsChangeLog entry per field that changed.
 */
export function usePodSettings() {
  const [settings, setSettings] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  // Latest optimistic state, readable synchronously from event handlers.
  const settingsRef = useRef(null);
  // Writes are chained so rapid changes land in order and each diff is
  // computed against the value the user was actually looking at.
  const queueRef = useRef(Promise.resolve());
  const pendingRef = useRef(0);
  const emailRef = useRef(undefined);

  const commit = useCallback((next) => {
    settingsRef.current = next;
    setSettings(next);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let retryTimer = null;

    const load = (attempt) =>
      loadOrCreateSettings()
        .then((record) => {
          if (cancelled) return;
          if (!record?.id) throw new Error("the server returned no settings record");
          setError(null);
          commit(withDefaults(record));
        })
        .catch((err) => {
          if (cancelled) return;
          console.error("Failed to load pod settings:", err);
          const delay = Math.min(RETRY_MAX_MS, RETRY_BASE_MS * 2 ** attempt);
          setError(
            userError(`Couldn’t reach the pod settings, retrying in ${delay / 1000}s.`, err),
          );
          retryTimer = setTimeout(() => load(attempt + 1), delay);
        });
    load(0);

    currentUserEmail().then((email) => {
      emailRef.current = email;
    });

    // Changes made from another phone/tablet/laptop show up live. While our
    // own writes are in flight we skip echoes so they can't clobber newer
    // optimistic values; the write's own response resyncs us afterwards.
    const unsubscribe = safeSubscribe(
      PodSettings,
      (event) => {
        const current = settingsRef.current;
        if (!current || event?.id !== current.id) return;
        if (event.type === "update" && event.data && pendingRef.current === 0) {
          commit({ ...current, ...event.data });
        }
      },
      "PodSettings",
    );

    return () => {
      cancelled = true;
      clearTimeout(retryTimer);
      unsubscribe();
    };
  }, [commit]);

  const applyChanges = useCallback(
    (patch) => {
      const current = settingsRef.current;
      if (!current || !patch || typeof patch !== "object") return;

      const changed = SETTINGS_FIELDS.filter(
        (field) => field in patch && patch[field] !== current[field],
      );
      if (changed.length === 0) return;

      const diff = Object.fromEntries(changed.map((f) => [f, patch[f]]));
      const logs = changed.map((field) => ({
        field_name: field,
        old_value: stringifyValue(current[field]),
        new_value: stringifyValue(patch[field]),
      }));

      commit({ ...current, ...diff });
      pendingRef.current += 1;
      setSaving(true);

      queueRef.current = queueRef.current.then(async () => {
        try {
          let saved;
          try {
            saved = await PodSettings.update(current.id, diff);
          } catch (err) {
            console.error("Failed to save settings:", err);
            // Roll back to whatever the server actually has.
            try {
              commit(withDefaults(await PodSettings.get(current.id)));
              setError(userError("Couldn’t save your change, so it was undone.", err));
            } catch (reloadErr) {
              console.error("Failed to reload settings after a failed save:", reloadErr);
              setError(
                userError(
                  "Couldn’t save your change, and the pod is unreachable. What’s shown may not match the pod.",
                  err,
                ),
              );
            }
            return;
          }

          setError(null);
          if (pendingRef.current === 1 && saved) {
            commit({ ...settingsRef.current, ...saved });
          }

          // The setting itself is saved; a failed history write shouldn't
          // undo it or claim the save failed.
          try {
            const changed_by = emailRef.current ?? null;
            await SettingsChangeLog.bulkCreate(
              logs.map((log) => ({ ...log, changed_by })),
            );
          } catch (err) {
            console.error("Failed to write change history:", err);
            setError(userError("Your change was saved, but the history log couldn’t be updated.", err));
          }
        } finally {
          pendingRef.current -= 1;
          if (pendingRef.current === 0) setSaving(false);
        }
      });
    },
    [commit],
  );

  return { settings, applyChanges, error, saving };
}
