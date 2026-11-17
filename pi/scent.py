"""
XRPod scent control: the Pi side of the ESP32 scent / IAQ node
(esp32/scent-node). Runs inside agent.py.

The node owns the hardware (3 scents x 2 diffusers, BME688). The Pi tells it
what to run over MQTT, using the topics and messages in docs/subsystems.md:

  Pi   --xrpod/scent/cmd---->  node   {"selected_scent": "pine", "scent_intensity_pct": 60}
  Pi  <--xrpod/scent/state---  node   what is actually running (retained)
  Pi  <--xrpod/scent/node----  node   "online" / "offline" (retained, last will)
  Pi  <--xrpod/scent/error---  node   {"error": "unknown_scent"} etc.
  Pi  <--xrpod/iaq/reading---  node   temperature, humidity, gas, scent_detected

The node turns everything off if it hears nothing for 15 s, so the Pi resends
the current command at least every CMD_REFRESH_S. The resend happens from the
control loop: if the loop hangs, the commands stop and the node fails safe.

By default this uses a stub link that only logs, so the agent runs on any
machine. On the Pi, set SCENT_HARDWARE=mqtt (the broker defaults to this Pi,
127.0.0.1:1883; change it with MQTT_HOST / MQTT_PORT, and MQTT_USER /
MQTT_PASSWORD if the broker needs a login).

Bench test with the node, without the rest of the agent:
    SCENT_HARDWARE=mqtt python3 scent.py lavender 60 20   # 60% for 20 s, then off
"""

import json
import logging
import math
import os
import sys
import threading
import time

log = logging.getLogger("xrpod.scent")

# Must match esp32/scent-node/include/config.h and docs/subsystems.md.
TOPIC_CMD = "xrpod/scent/cmd"
TOPIC_STATE = "xrpod/scent/state"
TOPIC_NODE = "xrpod/scent/node"
TOPIC_ERROR = "xrpod/scent/error"
TOPIC_READING = "xrpod/iaq/reading"

CMD_REFRESH_S = 5  # the node gives up after 15 s without a command
STATE_FRESH_S = 15  # the node publishes its state every 5 s
READING_FRESH_S = 15  # the node publishes a reading every 3 s

READING_NUMBERS = ("temp_c", "humidity_pct", "pressure_hpa", "gas_kohm", "gas_baseline_kohm")
READING_FLAGS = ("baseline_ready", "scent_detected")


# --------------------------------------------------------------------------
# Message validation (never trust the network)
# --------------------------------------------------------------------------
def _json(payload):
    try:
        return json.loads(payload)
    except (ValueError, UnicodeDecodeError):
        return None


def _number(value):
    """A finite float, or None. Rejects bools, strings, NaN and inf."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        value = float(value)
    except OverflowError:
        return None
    return value if math.isfinite(value) else None


def _short_str(value, limit=40):
    return value[:limit] if isinstance(value, str) else None


def parse_state(payload):
    """The node's state message, or None if it isn't a valid one."""
    data = _json(payload)
    if not isinstance(data, dict):
        return None
    scent = _short_str(data.get("selected_scent"))
    pct = _number(data.get("scent_intensity_pct"))
    if scent is None or pct is None or not 0 <= pct <= 100:
        return None
    diffusers = data.get("diffusers")
    if not isinstance(diffusers, list) or not all(isinstance(d, bool) for d in diffusers):
        diffusers = []
    return {
        "selected_scent": scent,
        "scent_intensity_pct": int(pct),
        "diffusers": diffusers[:4],
        "reason": _short_str(data.get("reason")) or "",
    }


def parse_reading(payload):
    """The node's IAQ reading, or None if it isn't one."""
    data = _json(payload)
    if not isinstance(data, dict):
        return None
    out = {k: _number(data.get(k)) for k in READING_NUMBERS}
    if all(v is None for v in out.values()):
        return None
    for k in READING_FLAGS:
        out[k] = data.get(k) is True
    return out


# --------------------------------------------------------------------------
# Links
# --------------------------------------------------------------------------
class StubLink:
    """Logs what it would send. Used when there's no broker."""

    is_stub = True

    def __init__(self):
        log.info("scent: STUB link (set SCENT_HARDWARE=mqtt on the Pi)")

    def publish(self, topic, payload, retain=False):
        log.debug("scent: would publish %s %s", topic, payload)
        return True

    def close(self):
        pass


def make_link(on_message):
    if os.environ.get("SCENT_HARDWARE", "").lower() != "mqtt":
        return StubLink()
    from mqtt import MqttClient

    client = MqttClient(
        os.environ.get("MQTT_HOST", "127.0.0.1"),
        int(os.environ.get("MQTT_PORT", "1883")),
        username=os.environ.get("MQTT_USER"),
        password=os.environ.get("MQTT_PASSWORD"),
        subscriptions=[TOPIC_STATE, TOPIC_NODE, TOPIC_ERROR, TOPIC_READING],
        on_message=on_message,
    )
    client.is_stub = False
    client.start()
    return client


# --------------------------------------------------------------------------
# Controller
# --------------------------------------------------------------------------
OFF = {"selected_scent": "none", "scent_intensity_pct": 0}


class ScentController:
    """Keeps the scent node running what the settings ask for."""

    def __init__(self, link=None, clock=time.monotonic):
        self.clock = clock
        self._lock = threading.Lock()
        self.node = "unknown"  # "online" / "offline" from the node's last will
        self.node_state, self._state_at = None, None
        self.reading, self._reading_at = None, None
        self.last_error = None
        self._last_cmd, self._last_sent = None, None
        self.link = link if link is not None else make_link(self.on_message)
        self.active = "none"  # what the Pi last asked for
        self.intensity = 0
        self.off()

    # ---- commands ----------------------------------------------------------
    def apply(self, scent, intensity_pct):
        """Run `scent` at `intensity_pct` (0-100). Call it every control loop.
        "none", 0% or anything that isn't a scent name all mean off. Names the
        node doesn't have are turned off by the node (it reports unknown_scent)."""
        intensity = max(0, min(100, int(intensity_pct)))
        if not isinstance(scent, str) or not scent or scent == "none" or intensity == 0:
            self.off()
            return
        self._send({"selected_scent": scent, "scent_intensity_pct": intensity})
        if scent != self.active:
            log.info("scent: %s at %s%%", scent, intensity)
        self.active, self.intensity = scent, intensity

    def off(self):
        self._send(OFF)
        if self.active != "none":
            log.info("scent: off")
        self.active, self.intensity = "none", 0

    def close(self):
        self._last_cmd = None  # force the final "off" out
        self.off()
        self.link.close()

    def _send(self, cmd):
        now = self.clock()
        if cmd == self._last_cmd and now - self._last_sent < CMD_REFRESH_S:
            return
        if self.link.publish(TOPIC_CMD, json.dumps(cmd)) is not False:
            self._last_cmd, self._last_sent = dict(cmd), now

    # ---- messages from the node (called on the MQTT thread) ----------------
    def on_message(self, topic, payload):
        now = self.clock()
        if topic == TOPIC_STATE:
            state = parse_state(payload)
            if state is None:
                log.warning("scent: ignoring bad state message")
                return
            with self._lock:
                self.node_state, self._state_at = state, now
        elif topic == TOPIC_READING:
            reading = parse_reading(payload)
            if reading is None:
                log.warning("scent: ignoring bad IAQ reading")
                return
            with self._lock:
                self.reading, self._reading_at = reading, now
        elif topic == TOPIC_NODE:
            text = payload.decode("utf-8", "replace").strip() if isinstance(payload, bytes) else str(payload)
            if text in ("online", "offline") and text != self.node:
                log.info("scent: node is %s", text)
                self.node = text
        elif topic == TOPIC_ERROR:
            data = _json(payload)
            error = _short_str(data.get("error")) if isinstance(data, dict) else None
            self.last_error = error or "unreadable error message"
            log.warning("scent: node reported %s", self.last_error)

    # ---- status for read_sensors() ------------------------------------------
    def reported_scent(self):
        """What is really running. With the stub link that's what we asked
        for; with the node it's the node's own report, and "none" if the
        node is offline or quiet (it turns itself off when it loses us)."""
        if getattr(self.link, "is_stub", False):
            return self.active
        with self._lock:
            state, at = self.node_state, self._state_at
        if self.node == "offline" or state is None or self.clock() - at > STATE_FRESH_S:
            return "none"
        return state["selected_scent"]

    def status(self):
        """Fields added to each sensor reading."""
        with self._lock:
            reading, at = self.reading, self._reading_at
        fresh = reading is not None and self.clock() - at <= READING_FRESH_S
        return {
            "scent_active": self.reported_scent(),
            "scent_node": "stub" if getattr(self.link, "is_stub", False) else self.node,
            "scent_detected": bool(fresh and reading["scent_detected"]),
            "iaq": dict(reading) if fresh else None,
        }


def _bench_test(argv):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    scent = argv[1] if len(argv) > 1 else "lavender"
    intensity = int(argv[2]) if len(argv) > 2 else 50
    seconds = float(argv[3]) if len(argv) > 3 else 10
    controller = ScentController()
    end = time.monotonic() + seconds
    try:
        while time.monotonic() < end:
            controller.apply(scent, intensity)  # resends, like the control loop
            print(controller.status(), "| node state:", controller.node_state)
            time.sleep(2)
    finally:
        controller.close()


if __name__ == "__main__":
    _bench_test(sys.argv)