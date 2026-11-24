"""
XRPod data store: settings, sensor readings, change history, events
(faults and status changes) and recording sessions in SQLite.

Validation lives here too, so a bad
request from any client (HUD, Unity, curl) is rejected before it can reach
the hardware.

Thread-safe: the web server and the control loop share one Store.
"""

import json
import sqlite3
import threading
import time
from datetime import datetime, timezone

SCENTS = ("none", "lavender", "pine", "citrus")  # must match the scent node (esp32/scent-node)
# Who is in charge: the researcher (manual) or the Pi's own control logic
# (auto). VR state never drives the hardware in manual mode.
CONTROL_MODES = ("manual", "auto")
# Which experience the headset shows. "none" means no environment picked.
ENVIRONMENTS = ("none", "beach", "forest", "desert", "sponsor")

# Fields whose value must be one of a fixed list.
CHOICES = {
    "selected_scent": SCENTS,
    "control_mode": CONTROL_MODES,
    "selected_environment": ENVIRONMENTS,
}

# field -> (kind, min, max). Mirrors src/lib/podSettings.js.
SETTINGS_SCHEMA = {
    "target_temp_f": ("number", 50, 95),
    "target_humidity_pct": ("number", 0, 100),
    "fan_speed_pct": ("int", 0, 100),
    "ac_on": ("bool", None, None),
    "heater_on": ("bool", None, None),
    "selected_scent": ("choice", None, None),
    "scent_intensity_pct": ("int", 0, 100),
    "control_mode": ("choice", None, None),
    "selected_environment": ("choice", None, None),
}

DEFAULT_SETTINGS = {
    "target_temp_f": 72,
    "target_humidity_pct": 45,
    "fan_speed_pct": 0,
    "ac_on": False,
    "heater_on": False,
    "selected_scent": "none",
    "scent_intensity_pct": 50,
    "control_mode": "manual",
    "selected_environment": "none",
}

# Fields that drive the hardware. Who may change them depends on the mode:
# the researcher (HUD, Unity, curl) only in manual, the Pi's own auto control
# logic only in auto. The mode and environment are not in this list, so the
# researcher can always switch back to manual and take control.
HARDWARE_FIELDS = (
    "target_temp_f",
    "target_humidity_pct",
    "fan_speed_pct",
    "ac_on",
    "heater_on",
    "selected_scent",
    "scent_intensity_pct",
)

# Keep the database small on the Pi's SD card. Readings recorded during a
# session are kept until the session is deleted, whatever their age.
READING_RETENTION_SECONDS = 24 * 60 * 60
HISTORY_MAX_ROWS = 5000
EVENT_MAX_ROWS = 5000
MAX_CHANGED_BY_LENGTH = 64

# Events: what happened, how bad, and which part of the pod it was.
EVENT_LEVELS = ("info", "warning", "error")
MAX_EVENT_TEXT = 200
MAX_SESSION_NAME = 64
SESSION_LIST_LIMIT = 100


class ValidationError(ValueError):
    pass


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _validate_value(field, value):
    kind, lo, hi = SETTINGS_SCHEMA[field]
    if kind == "bool":
        if not isinstance(value, bool):
            raise ValidationError(f"{field} must be true or false")
        return value
    if kind == "choice":
        options = CHOICES[field]
        if not isinstance(value, str) or value not in options:
            raise ValidationError(f"{field} must be one of {', '.join(options)}")
        return value
    # number / int: reject bools (True is an int in Python), NaN and inf.
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        raise ValidationError(f"{field} must be a number")
    if kind == "int":
        if value != int(value):
            raise ValidationError(f"{field} must be a whole number")
        value = int(value)
    if not lo <= value <= hi:
        raise ValidationError(f"{field} must be between {lo} and {hi}")
    return value


def validate_patch(patch, current, by_auto=False):
    """Return a cleaned patch, or raise ValidationError.

    Enforces heater/AC mutual exclusion: turning one on turns the other off,
    and asking for both on at once is rejected.

    Enforces the mode lock (KAN-49): in auto mode only the auto control logic
    (by_auto=True) may change the hardware fields; in manual mode only the
    researcher may. Only the researcher may change the control mode.
    """
    if not isinstance(patch, dict) or not patch:
        raise ValidationError("body must be a non-empty JSON object")
    unknown = sorted(set(patch) - set(SETTINGS_SCHEMA))
    if unknown:
        raise ValidationError(f"unknown field(s): {', '.join(unknown)}")

    clean = {field: _validate_value(field, value) for field, value in patch.items()}

    if clean.get("heater_on") and clean.get("ac_on"):
        raise ValidationError("heater_on and ac_on can't both be true")
    if clean.get("heater_on") and current.get("ac_on"):
        clean.setdefault("ac_on", False)
    if clean.get("ac_on") and current.get("heater_on"):
        clean.setdefault("heater_on", False)

    if by_auto and "control_mode" in clean:
        raise ValidationError("only the researcher can change control_mode")
    mode = clean.get("control_mode", current.get("control_mode", "manual"))
    changing = sorted(f for f in HARDWARE_FIELDS if f in clean and clean[f] != current.get(f))
    if changing and mode == "auto" and not by_auto:
        raise ValidationError(
            f"pod is in auto mode: switch to manual to change {', '.join(changing)}"
        )
    if changing and mode == "manual" and by_auto:
        raise ValidationError(
            f"pod is in manual mode: auto control can't change {', '.join(changing)}"
        )
    return clean


def _stringify(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class Store:
    def __init__(self, path):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(
            """
            PRAGMA journal_mode = WAL;
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                data TEXT NOT NULL,
                updated_date TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_ts REAL NOT NULL,
                created_date TEXT NOT NULL,
                data TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS readings_ts ON readings (created_ts);
            CREATE TABLE IF NOT EXISTS change_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_date TEXT NOT NULL,
                field_name TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT NOT NULL,
                changed_by TEXT
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_ts REAL NOT NULL,
                created_date TEXT NOT NULL,
                level TEXT NOT NULL,
                source TEXT NOT NULL,
                message TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS events_ts ON events (created_ts);
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                started_ts REAL NOT NULL,
                started_date TEXT NOT NULL,
                ended_ts REAL,
                ended_date TEXT
            );
            """
        )
        self._settings = self._load_settings()
        self._readings_since_prune = 0

    # ---------------------------------------------------------------- settings
    def _load_settings(self):
        row = self._db.execute("SELECT data, updated_date FROM settings WHERE id = 1").fetchone()
        if row is None:
            settings = dict(DEFAULT_SETTINGS)
            updated = now_iso()
            with self._db:
                self._db.execute(
                    "INSERT INTO settings (id, data, updated_date) VALUES (1, ?, ?)",
                    (json.dumps(settings), updated),
                )
        else:
            stored = json.loads(row["data"])
            # Fill in fields added after this database was created; drop
            # anything that no longer validates.
            settings = dict(DEFAULT_SETTINGS)
            for field, value in stored.items():
                if field in SETTINGS_SCHEMA:
                    try:
                        settings[field] = _validate_value(field, value)
                    except ValidationError:
                        pass
            updated = row["updated_date"]
        return {**settings, "updated_date": updated}

    def get_settings(self):
        with self._lock:
            return dict(self._settings)

    def update_settings(self, patch, changed_by=None, by_auto=False):
        """Validate and save `patch`. Returns (settings, new_history_rows).

        Pass by_auto=True from the auto control logic; everything else (HUD,
        Unity, curl) is the researcher. See validate_patch() for the mode lock.
        """
        if changed_by is not None:
            changed_by = str(changed_by)[:MAX_CHANGED_BY_LENGTH]
        with self._lock:
            current = self._settings
            clean = validate_patch(patch, current, by_auto=by_auto)
            changed = [f for f in SETTINGS_SCHEMA if f in clean and clean[f] != current[f]]
            if not changed:
                return dict(current), []

            updated = now_iso()
            new = {**current, **{f: clean[f] for f in changed}, "updated_date": updated}
            data = {f: new[f] for f in SETTINGS_SCHEMA}
            rows = []
            with self._db:
                self._db.execute(
                    "UPDATE settings SET data = ?, updated_date = ? WHERE id = 1",
                    (json.dumps(data), updated),
                )
                for field in changed:
                    cur = self._db.execute(
                        "INSERT INTO change_log (created_date, field_name, old_value, new_value, changed_by)"
                        " VALUES (?, ?, ?, ?, ?)",
                        (updated, field, _stringify(current[field]), _stringify(new[field]), changed_by),
                    )
                    rows.append({
                        "id": str(cur.lastrowid),
                        "created_date": updated,
                        "field_name": field,
                        "old_value": _stringify(current[field]),
                        "new_value": _stringify(new[field]),
                        "changed_by": changed_by,
                    })
                self._db.execute(
                    "DELETE FROM change_log WHERE id <= (SELECT MAX(id) FROM change_log) - ?",
                    (HISTORY_MAX_ROWS,),
                )
            self._settings = new
            return dict(new), rows

    # ----------------------------------------------------------------- history
    def get_history(self, limit=50):
        limit = max(1, min(500, int(limit)))
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM change_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{**dict(r), "id": str(r["id"])} for r in rows]

    # ---------------------------------------------------------------- readings
    def add_reading(self, reading):
        ts = time.time()
        created = now_iso()
        with self._lock, self._db:
            cur = self._db.execute(
                "INSERT INTO readings (created_ts, created_date, data) VALUES (?, ?, ?)",
                (ts, created, json.dumps(reading)),
            )
            self._readings_since_prune += 1
            if self._readings_since_prune >= 500:
                self._readings_since_prune = 0
                self._prune_readings(ts - READING_RETENTION_SECONDS)
        return {**reading, "id": str(cur.lastrowid), "created_date": created}

    def _prune_readings(self, before_ts):
        """Drop readings older than before_ts, except those recorded during a
        session. Call with the lock held, inside a transaction."""
        self._db.execute(
            "DELETE FROM readings WHERE created_ts < ? AND NOT EXISTS ("
            " SELECT 1 FROM sessions s WHERE readings.created_ts >= s.started_ts"
            " AND (s.ended_ts IS NULL OR readings.created_ts <= s.ended_ts))",
            (before_ts,),
        )

    def get_latest_reading(self):
        with self._lock:
            row = self._db.execute(
                "SELECT id, created_date, data FROM readings ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return {**json.loads(row["data"]), "id": str(row["id"]), "created_date": row["created_date"]}

    def readings_between(self, start_ts, end_ts):
        """Readings from start_ts to end_ts (seconds since 1970), oldest
        first, each with its created_date."""
        with self._lock:
            rows = self._db.execute(
                "SELECT created_date, data FROM readings WHERE created_ts >= ? AND created_ts <= ?"
                " ORDER BY id",
                (start_ts, end_ts),
            ).fetchall()
        return [{**json.loads(r["data"]), "created_date": r["created_date"]} for r in rows]

    # ------------------------------------------------------------------ events
    def add_event(self, level, source, message):
        """Record something that happened (a node going offline, a fault,
        the Pi starting). Returns the new row."""
        if level not in EVENT_LEVELS:
            raise ValidationError(f"level must be one of {', '.join(EVENT_LEVELS)}")
        source = str(source)[:32] or "pi"
        message = str(message)[:MAX_EVENT_TEXT]
        ts = time.time()
        created = now_iso()
        with self._lock, self._db:
            cur = self._db.execute(
                "INSERT INTO events (created_ts, created_date, level, source, message) VALUES (?, ?, ?, ?, ?)",
                (ts, created, level, source, message),
            )
            self._db.execute(
                "DELETE FROM events WHERE id <= (SELECT MAX(id) FROM events) - ?", (EVENT_MAX_ROWS,)
            )
        return {"id": str(cur.lastrowid), "created_date": created, "level": level,
                "source": source, "message": message}

    def get_events(self, limit=100, min_level="info"):
        """Newest events first. min_level "warning" leaves out info."""
        limit = max(1, min(500, int(limit)))
        if min_level not in EVENT_LEVELS:
            raise ValidationError(f"level must be one of {', '.join(EVENT_LEVELS)}")
        levels = EVENT_LEVELS[EVENT_LEVELS.index(min_level):]
        marks = ",".join("?" * len(levels))
        with self._lock:
            rows = self._db.execute(
                f"SELECT id, created_date, level, source, message FROM events WHERE level IN ({marks})"  # noqa: S608 - only "?" marks
                " ORDER BY id DESC LIMIT ?",
                (*levels, limit),
            ).fetchall()
        return [{**dict(r), "id": str(r["id"])} for r in rows]

    def events_between(self, start_ts, end_ts):
        """Events and settings changes from start_ts to end_ts, oldest first,
        as one list of {created_date, level, source, message}."""
        start_iso = datetime.fromtimestamp(start_ts, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        end_iso = datetime.fromtimestamp(end_ts, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        with self._lock:
            events = self._db.execute(
                "SELECT created_date, level, source, message FROM events"
                " WHERE created_ts >= ? AND created_ts <= ? ORDER BY id",
                (start_ts, end_ts),
            ).fetchall()
            changes = self._db.execute(
                "SELECT created_date, field_name, old_value, new_value, changed_by FROM change_log"
                " WHERE created_date >= ? AND created_date <= ? ORDER BY id",
                (start_iso, end_iso),
            ).fetchall()
        rows = [dict(e) for e in events]
        for c in changes:
            by = f" (by {c['changed_by']})" if c["changed_by"] else ""
            rows.append({
                "created_date": c["created_date"],
                "level": "info",
                "source": "settings",
                "message": f"{c['field_name']}: {c['old_value']} -> {c['new_value']}{by}",
            })
        rows.sort(key=lambda r: r["created_date"])
        return rows

    # ---------------------------------------------------------------- sessions
    def _session_view(self, row):
        if row is None:
            return None
        end = row["ended_ts"] if row["ended_ts"] is not None else time.time()
        with_counts = self._db.execute(
            "SELECT COUNT(*) FROM readings WHERE created_ts >= ? AND created_ts <= ?",
            (row["started_ts"], end),
        ).fetchone()[0]
        return {
            "id": str(row["id"]),
            "name": row["name"],
            "started_date": row["started_date"],
            "ended_date": row["ended_date"],
            "recording": row["ended_ts"] is None,
            "duration_s": round(end - row["started_ts"]),
            "readings": with_counts,
        }

    def start_session(self, name=None):
        """Start recording. Only one session records at a time."""
        if name is not None and not isinstance(name, str):
            raise ValidationError("name must be text")
        name = (name or "").strip()[:MAX_SESSION_NAME]
        with self._lock, self._db:
            if self._db.execute("SELECT 1 FROM sessions WHERE ended_ts IS NULL").fetchone():
                raise ValidationError("a session is already recording: stop it first")
            ts, created = time.time(), now_iso()
            cur = self._db.execute(
                "INSERT INTO sessions (name, started_ts, started_date) VALUES (?, ?, ?)",
                (name or f"Session {created[:16].replace('T', ' ')}", ts, created),
            )
            row = self._db.execute("SELECT * FROM sessions WHERE id = ?", (cur.lastrowid,)).fetchone()
            return self._session_view(row)

    def stop_session(self):
        """Stop the session that's recording. Returns it."""
        with self._lock, self._db:
            row = self._db.execute("SELECT * FROM sessions WHERE ended_ts IS NULL").fetchone()
            if row is None:
                raise ValidationError("no session is recording")
            self._db.execute(
                "UPDATE sessions SET ended_ts = ?, ended_date = ? WHERE id = ?",
                (time.time(), now_iso(), row["id"]),
            )
            row = self._db.execute("SELECT * FROM sessions WHERE id = ?", (row["id"],)).fetchone()
            return self._session_view(row)

    def get_sessions(self, limit=SESSION_LIST_LIMIT):
        """Newest first, the recording one (if any) included."""
        limit = max(1, min(SESSION_LIST_LIMIT, int(limit)))
        with self._lock:
            rows = self._db.execute("SELECT * FROM sessions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [self._session_view(r) for r in rows]

    def get_session_range(self, session_id):
        """(name, start_ts, end_ts) of a session; end is now while it records."""
        try:
            session_id = int(session_id)
        except (TypeError, ValueError) as err:
            raise ValidationError("session must be a number") from err
        with self._lock:
            row = self._db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise ValidationError("no such session")
        end = row["ended_ts"] if row["ended_ts"] is not None else time.time()
        return row["name"], row["started_ts"], end

    def delete_session(self, session_id):
        """Forget a stopped session; its readings then age out normally."""
        name, _, _ = self.get_session_range(session_id)
        with self._lock, self._db:
            cur = self._db.execute(
                "DELETE FROM sessions WHERE id = ? AND ended_ts IS NOT NULL", (int(session_id),)
            )
            if cur.rowcount == 0:
                raise ValidationError("stop the session before deleting it")
            self._prune_readings(time.time() - READING_RETENTION_SECONDS)
        return name

    def close(self):
        with self._lock:
            self._db.close()
