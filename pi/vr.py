"""
XRPod VR state: what the headset last reported (environment and zone).

The Unity app sends PUT /api/vr/state whenever the environment or zone
changes, and repeats its latest message every ~5 s. Each message is the full
current state, so the Pi only keeps the newest one, in memory (it can arrive
several times a second, so it is not a database row per step).

The headset only reports. It never sends fan/heater/AC/scent values, and in
manual mode nothing here changes the hardware. In auto mode the control
logic can read latest() and decide what to do.

Message format: Maryam's "Proposal: how the Pi and the VR app talk"
(vr/docs/POD_PROTOCOL_PROPOSAL.md).

Live view: the headset also sends a small JPEG of what the user sees, a few
times a second (PUT /api/vr/frame). Only the newest picture is kept, in
memory, for the HUD to show (GET /api/vr/frame). It is never saved.
"""

import base64
import binascii
import threading
import time

from store import ValidationError, now_iso

# "none": the headset is in its waiting room (no world picked in the HUD).
VR_ENVIRONMENTS = ("none", "beach", "forest", "desert", "sponsor")
ZONE_TYPES = ("neutral", "hot", "cool", "windy")
REASONS = ("environment_changed", "zone_entered", "zone_exited")
FIELDS = ("session_id", "seq", "environment", "zone_id", "zone_type", "zone_tracking", "reason")
MAX_TEXT = 64

# After this long with no message, the HUD shows "VR: not connected" and
# auto mode should treat VR as neutral.
STALE_SECONDS = 15


def _text(field, value, allow_none=False):
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not 1 <= len(value) <= MAX_TEXT:
        raise ValidationError(f"{field} must be text, 1 to {MAX_TEXT} characters")
    return value


def _choice(field, value, options):
    if not isinstance(value, str) or value not in options:
        raise ValidationError(f"{field} must be one of {', '.join(options)}")
    return value


def validate_vr_state(msg):
    """Return a cleaned copy of a headset message, or raise ValidationError.
    All fields are required and unknown fields are rejected."""
    if not isinstance(msg, dict):
        raise ValidationError("body must be a JSON object")
    unknown = sorted(set(msg) - set(FIELDS))
    if unknown:
        raise ValidationError(f"unknown field(s): {', '.join(unknown)}")
    missing = [f for f in FIELDS if f not in msg]
    if missing:
        raise ValidationError(f"missing field(s): {', '.join(missing)}")

    seq = msg["seq"]
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1:
        raise ValidationError("seq must be a whole number, 1 or more")
    if not isinstance(msg["zone_tracking"], bool):
        raise ValidationError("zone_tracking must be true or false")

    clean = {
        "session_id": _text("session_id", msg["session_id"]),
        "seq": seq,
        "environment": _choice("environment", msg["environment"], VR_ENVIRONMENTS),
        "zone_id": _text("zone_id", msg["zone_id"], allow_none=True),
        "zone_type": _choice("zone_type", msg["zone_type"], ZONE_TYPES),
        "zone_tracking": msg["zone_tracking"],
        "reason": _choice("reason", msg["reason"], REASONS),
    }
    if clean["zone_id"] is None and clean["zone_type"] != "neutral":
        raise ValidationError("zone_type must be neutral when zone_id is null")
    if not clean["zone_tracking"] and clean["zone_id"] is not None:
        raise ValidationError("zone_id must be null when zone_tracking is false")
    if clean["environment"] == "none" and clean["zone_tracking"]:
        raise ValidationError("zone_tracking must be false in the waiting room (environment none)")
    return clean


class VrState:
    """Thread-safe holder for the newest headset message."""

    def __init__(self, clock=time.monotonic):
        self._lock = threading.Lock()
        self._clock = clock
        self._state = None  # cleaned message + received_date
        self._received_at = None  # clock() value, for staleness

    def update(self, msg):
        """Validate and store `msg`. Returns (state, changed). Within one
        session_id:
          - a higher seq is new: stored (changed=True);
          - the same seq is the headset's ~5 s repeat: the state is kept, but
            it counts as hearing from the headset, so it stays connected
            while the user stands still (changed=False);
          - a lower seq arrived late: ignored (changed=False).
        A new session_id means the app restarted, so it is accepted whatever
        its seq."""
        clean = validate_vr_state(msg)
        with self._lock:
            old = self._state
            if old and old["session_id"] == clean["session_id"] and clean["seq"] <= old["seq"]:
                if clean["seq"] == old["seq"]:
                    self._state = {**old, "received_date": now_iso()}
                    self._received_at = self._clock()
                return self._view(), False
            self._state = {**clean, "received_date": now_iso()}
            self._received_at = self._clock()
            return self._view(), True

    def latest(self):
        """The newest state plus age_s and connected, or None before the
        headset has sent anything."""
        with self._lock:
            return self._view()

    def _view(self):
        if self._state is None:
            return None
        age = max(0.0, self._clock() - self._received_at)
        return {**self._state, "age_s": round(age, 1), "connected": age <= STALE_SECONDS}


# ------------------------------------------------------------- live view

# A 640 x 360 JPEG at the headset's quality is ~20-60 KB; this leaves room.
MAX_FRAME_BYTES = 150 * 1024
# Base64 makes it a third bigger, plus the JSON around it.
MAX_FRAME_BODY_BYTES = 256 * 1024
# The HUD stops showing a picture this long after the last one.
FRAME_STALE_SECONDS = 3


def decode_frame(msg):
    """Return the JPEG bytes in a {"jpeg_base64": "..."} message, or raise
    ValidationError. Only a real JPEG within MAX_FRAME_BYTES is accepted."""
    if not isinstance(msg, dict) or set(msg) != {"jpeg_base64"}:
        raise ValidationError('body must be {"jpeg_base64": "..."}')
    text = msg["jpeg_base64"]
    if not isinstance(text, str) or not text:
        raise ValidationError("jpeg_base64 must be base64 text")
    try:
        image = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as err:
        raise ValidationError("jpeg_base64 must be base64 text") from err
    if len(image) > MAX_FRAME_BYTES:
        raise ValidationError(f"picture too large (over {MAX_FRAME_BYTES // 1024} KB)")
    # A JPEG starts with FF D8 FF and ends with FF D9.
    if not (image.startswith(b"\xff\xd8\xff") and image.endswith(b"\xff\xd9")):
        raise ValidationError("picture must be a JPEG")
    return image


class VrFrame:
    """Thread-safe holder for the newest live-view picture."""

    def __init__(self, clock=time.monotonic):
        self._lock = threading.Lock()
        self._clock = clock
        self._image = None
        self._received_at = None

    def update(self, msg):
        """Validate and keep the picture in `msg` (see decode_frame)."""
        image = decode_frame(msg)
        with self._lock:
            self._image = image
            self._received_at = self._clock()

    def latest(self):
        """The newest JPEG, or None if there's none from the last
        FRAME_STALE_SECONDS (the headset stopped sending or is off)."""
        with self._lock:
            if self._image is None or self._clock() - self._received_at > FRAME_STALE_SECONDS:
                return None
            return self._image
