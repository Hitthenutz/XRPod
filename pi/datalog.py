"""
XRPod data logging (punch list feature 7).

Every control loop the Pi saves one reading (store.add_reading): sensor
values, actuator states, the operating mode, the world and what the headset
reports, with a timestamp, once a second. On top of that this module

  * notices changes between readings and turns them into events: a node
    going offline or coming back, the BME688 stopping, the headset
    disconnecting, the heater / AC / scent switching, node error reports
    (EventWatcher). Events are saved in the store and shown live in the HUD;
  * writes readings and events as CSV files for a time range or a recorded
    session (readings_csv, events_csv).

Standard library only.
"""

import csv
import io
import re

# Columns that come first in the readings CSV, in this order. Anything else a
# reading contains follows, sorted, so new fields show up without code changes.
FIRST_COLUMNS = (
    "created_date",
    "control_mode",
    "selected_environment",
    "vr_connected",
    "vr_environment",
    "vr_zone",
    "actual_temp_f",
    "actual_humidity_pct",
    "climate_source",
    "heater_running",
    "ac_running",
    "fan_rpm",
    "fan_node",
    "scent_active",
    "scent_node",
    "scent_detected",
)

NODE_NAMES = {"scent_node": "Scent node", "fan_node": "Fan node"}


class EventWatcher:
    """Compares each reading with the one before and says what changed.

    check() returns a list of (level, source, message). The first reading
    only reports problems (a node that's offline at start-up), not every
    state as a change.
    """

    def __init__(self):
        self._last = None

    def check(self, reading, vr=None, node_errors=()):
        vr = vr or {}
        now = {
            "scent_node": reading.get("scent_node"),
            "fan_node": reading.get("fan_node"),
            "iaq": reading.get("iaq") is not None,
            "vr": bool(vr.get("connected")),
            "vr_environment": vr.get("environment"),
            "heater": bool(reading.get("heater_running")),
            "ac": bool(reading.get("ac_running")),
            "scent": reading.get("scent_active") or "none",
        }
        before, first = self._last, self._last is None
        self._last = now
        events = []

        for key, name in NODE_NAMES.items():
            state = now[key]
            if state in (None, "stub", "unknown"):
                continue
            if first:
                if state == "offline":
                    events.append(("warning", key[:-5], f"{name} is offline"))
            elif state != before[key]:
                if state == "offline":
                    events.append(("warning", key[:-5], f"{name} went offline (its outputs turn off)"))
                else:
                    events.append(("info", key[:-5], f"{name} is online"))

        for source, message in node_errors:
            events.append(("warning", source, f"{source.capitalize()} node reported: {message}"))

        if not first:
            if now["iaq"] != before["iaq"]:
                events.append(("info", "iaq", "BME688 sensor is reporting") if now["iaq"] else
                              ("warning", "iaq", "BME688 sensor stopped reporting (temperature and humidity are simulated)"))
            if now["vr"] != before["vr"]:
                events.append(("info", "vr", f"Headset connected ({now['vr_environment'] or 'no world'})")
                              if now["vr"] else ("warning", "vr", "Headset disconnected"))
            for key, name in (("heater", "Heater"), ("ac", "AC")):
                if now[key] != before[key]:
                    events.append(("info", key, f"{name} {'on' if now[key] else 'off'}"))
            if now["scent"] != before["scent"]:
                events.append(("info", "scent", "Scent off" if now["scent"] == "none" else f"Scent now {now['scent']}"))
        return events


# ------------------------------------------------------------------ CSV files

def _flatten(reading, prefix=""):
    """{"iaq": {"temp_c": 22}} -> {"iaq_temp_c": 22}."""
    flat = {}
    for key, value in reading.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{name}_"))
        elif value is None or isinstance(value, (str, int, float, bool)):
            flat[name] = value
    return flat


def _cell(value):
    """One CSV cell. Text that a spreadsheet would run as a formula
    (=, +, -, @ at the start) gets a leading apostrophe."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def readings_csv(readings):
    """Readings (oldest first) as CSV text: FIRST_COLUMNS, then every other
    field any reading has. Nested values (the BME688's iaq) are flattened."""
    rows = [_flatten({k: v for k, v in r.items() if k != "id"}) for r in readings]
    extra = sorted({k for row in rows for k in row} - set(FIRST_COLUMNS))
    columns = list(FIRST_COLUMNS) + extra
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_cell(row.get(c)) for c in columns])
    return out.getvalue()


def events_csv(events):
    """Events and settings changes (oldest first) as CSV text."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["created_date", "level", "source", "message"])
    for e in events:
        writer.writerow([_cell(e.get(k)) for k in ("created_date", "level", "source", "message")])
    return out.getvalue()


def file_name(label, kind):
    """A safe download name, e.g. xrpod-session-3-trial-a-readings.csv."""
    slug = re.sub(r"[^a-z0-9]+", "-", str(label).lower()).strip("-")[:48] or "data"
    return f"xrpod-{slug}-{kind}.csv"
