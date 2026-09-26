import { useCallback, useEffect, useRef, useState } from "react";
import { base44 } from "@/api/base44Client";
import {
  DEFAULT_SETTINGS,
  SETTINGS_FIELDS,
  stringifyValue,
} from "@/lib/podSettings";

const PodSettings = base44.entities.PodSettings;
const SettingsChangeLog = base44.entities.SettingsChangeLog;

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
    loadOrCreateSettings()
      .then((record) => !cancelled && commit(record))
      .catch((err) => !cancelled && setError(err));

    currentUserEmail().then((email) => {
      emailRef.current = email;
    });

    // Changes made from another phone/tablet/laptop show up live. While our
    // own writes are in flight we skip echoes so they can't clobber newer
    // optimistic values; the write's own response resyncs us afterwards.
    const unsubscribe = PodSettings.subscribe((event) => {
      const current = settingsRef.current;
      if (!current || event.id !== current.id) return;
      if (event.type === "update" && pendingRef.current === 0) {
        commit({ ...current, ...event.data });
      }
    });

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [commit]);

  const applyChanges = useCallback(
    (patch) => {
      const current = settingsRef.current;
      if (!current) return;

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
          const saved = await PodSettings.update(current.id, diff);
          const changed_by = emailRef.current ?? null;
          await SettingsChangeLog.bulkCreate(
            logs.map((log) => ({ ...log, changed_by })),
          );
          setError(null);
          if (pendingRef.current === 1 && saved) {
            commit({ ...settingsRef.current, ...saved });
          }
        } catch (err) {
          console.error("Failed to save settings:", err);
          setError(err);
          // Roll back to whatever the server actually has.
          try {
            commit(await PodSettings.get(current.id));
          } catch {
            /* keep optimistic state; error banner is showing */
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
