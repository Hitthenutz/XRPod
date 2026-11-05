"""
XRPod data store: settings, sensor readings and change history in SQLite.

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

SCENTS = ("none", "lavender", "pine", "citrus", "ocean", "rain")

# field -> (kind, min, max). Mirrors src/lib/podSettings.js.
SETTINGS_SCHEMA = {
    "target_temp_f": ("number", 50, 95),
    "target_humidity_pct": ("number", 0, 100),
    "fan_speed_pct": ("int", 0, 100),
    "ac_on": ("bool", None, None),
    "heater_on": ("bool", None, None),
    "selected_scent": ("scent", None, None),
    "scent_intensity_pct": ("int", 0, 100),
}

DEFAULT_SETTINGS = {
    "target_temp_f": 72,
    "target_humidity_pct": 45,
    "fan_speed_pct": 0,
    "ac_on": False,
    "heater_on": False,
    "selected_scent": "none",
    "scent_intensity_pct": 50,
}

# Keep the database small on the Pi's SD card.
READING_RETENTION_SECONDS = 24 * 60 * 60
HISTORY_MAX_ROWS = 5000
MAX_CHANGED_BY_LENGTH = 64


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
    if kind == "scent":
        if value not in SCENTS:
            raise ValidationError(f"{field} must be one of {', '.join(SCENTS)}")
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


def validate_patch(patch, current):
    """Return a cleaned patch, or raise ValidationError.

    Enforces heater/AC mutual exclusion: turning one on turns the other off,
    and asking for both on at once is rejected.
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

    def update_settings(self, patch, changed_by=None):
        """Validate and save `patch`. Returns (settings, new_history_rows)."""
        if changed_by is not None:
            changed_by = str(changed_by)[:MAX_CHANGED_BY_LENGTH]
        with self._lock:
            current = self._settings
            clean = validate_patch(patch, current)
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
                self._db.execute(
                    "DELETE FROM readings WHERE created_ts < ?", (ts - READING_RETENTION_SECONDS,)
                )
        return {**reading, "id": str(cur.lastrowid), "created_date": created}

    def get_latest_reading(self):
        with self._lock:
            row = self._db.execute(
                "SELECT id, created_date, data FROM readings ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return {**json.loads(row["data"]), "id": str(row["id"]), "created_date": row["created_date"]}

    def close(self):
        with self._lock:
            self._db.close()
