"""
XRPod fan control: the Pi side of the ESP32 fan node (esp32/fan-node).
Runs inside agent.py, the same way scent.py runs the scent node.

The node owns the fans (Corsair RS120, 4-pin PWM, daisy-chained) and reads
their tach. The Pi tells it what speed to run over MQTT, using the topics in
docs/subsystems.md:

  Pi   --xrpod/fan/cmd---->  node   {"fan_speed_pct": 60}
  Pi  <--xrpod/fan/state---  node   {"fan_speed_pct", "fan_rpm", "uptime_s"} (retained)
  Pi  <--xrpod/fan/node----  node   "online" / "offline" (retained, last will)
  Pi  <--xrpod/fan/error---  node   {"error": "bad_json"} etc.

The node turns the fans off if it hears nothing for 15 s, so the Pi resends
the current speed at least every CMD_REFRESH_S. The resend happens from the
control loop: if the loop hangs, the commands stop and the node fails safe.

By default this uses a stub link that only logs, so the agent runs on any
machine. On the Pi, set FAN_HARDWARE=mqtt (same broker settings as the scent
node: MQTT_HOST / MQTT_PORT, MQTT_USER / MQTT_PASSWORD).

Bench test with the node, without the rest of the agent:
    FAN_HARDWARE=mqtt python3 fan.py 60 20   # 60% for 20 s, then off
"""

import json
import logging
import math
import os
import sys
import threading
import time

log = logging.getLogger("xrpod.fan")

# Must match esp32/fan-node/fan-node.ino and docs/subsystems.md.
TOPIC_CMD = "xrpod/fan/cmd"
TOPIC_STATE = "xrpod/fan/state"
TOPIC_NODE = "xrpod/fan/node"
TOPIC_ERROR = "xrpod/fan/error"

CMD_REFRESH_S = 5  # the node gives up after 15 s without a command
STATE_FRESH_S = 15  # the node publishes its state every 2 s
MAX_RPM = 10_000  # far above any 120 mm fan; anything higher is noise


# --------------------------------------------------------------------------
# Message validation (never trust the network)
# --------------------------------------------------------------------------
def _number(value):
    """A finite float, or None. Rejects bools, strings, NaN and inf."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        value = float(value)
    except OverflowError:
        return None
    return value if math.isfinite(value) else None


def parse_state(payload):
    """The node's state message, or None if it isn't a valid one."""
    try:
        data = json.loads(payload)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    pct = _number(data.get("fan_speed_pct"))
    rpm = _number(data.get("fan_rpm"))
    if pct is None or rpm is None or not 0 <= pct <= 100 or not 0 <= rpm <= MAX_RPM:
        return None
    return {"fan_speed_pct": int(pct), "fan_rpm": int(rpm)}


# --------------------------------------------------------------------------
# Links
# --------------------------------------------------------------------------
class StubLink:
    """Logs what it would send. Used when there's no broker."""

    is_stub = True

    def __init__(self):
        log.info("fan: STUB link (set FAN_HARDWARE=mqtt on the Pi)")

    def publish(self, topic, payload, retain=False):
        log.debug("fan: would publish %s %s", topic, payload)
        return True

    def close(self):
        pass


def make_link(on_message):
    if os.environ.get("FAN_HARDWARE", "").lower() != "mqtt":
        return StubLink()
    from mqtt import MqttClient

    client = MqttClient(
        os.environ.get("MQTT_HOST", "127.0.0.1"),
        int(os.environ.get("MQTT_PORT", "1883")),
        client_id="xrpod-pi-fan-" + os.urandom(3).hex(),
        username=os.environ.get("MQTT_USER"),
        password=os.environ.get("MQTT_PASSWORD"),
        subscriptions=[TOPIC_STATE, TOPIC_NODE, TOPIC_ERROR],
        on_message=on_message,
    )
    client.is_stub = False
    client.start()
    return client


# --------------------------------------------------------------------------
# Controller
# --------------------------------------------------------------------------
class FanController:
    """Keeps the fan node running at the speed the settings ask for."""

    def __init__(self, link=None, clock=time.monotonic):
        self.clock = clock
        self._lock = threading.Lock()
        self.node = "unknown"  # "online" / "offline" from the node's last will
        self.node_state, self._state_at = None, None
        self.last_error = None
        self._last_cmd, self._last_sent = None, None
        self.link = link if link is not None else make_link(self.on_message)
        self.speed = 0  # what the Pi last asked for
        self.set_speed(0)

    # ---- commands ----------------------------------------------------------
    def set_speed(self, pct):
        """Run the fans at `pct` (0-100). Call it every control loop."""
        pct = max(0, min(100, int(pct)))
        self._send({"fan_speed_pct": pct})
        if pct != self.speed:
            log.info("fan: %s%%", pct)
        self.speed = pct

    def close(self):
        self._last_cmd = None  # force the final "off" out
        self.set_speed(0)
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
                log.warning("fan: ignoring bad state message")
                return
            with self._lock:
                self.node_state, self._state_at = state, now
        elif topic == TOPIC_NODE:
            text = payload.decode("utf-8", "replace").strip() if isinstance(payload, bytes) else str(payload)
            if text in ("online", "offline") and text != self.node:
                log.info("fan: node is %s", text)
                self.node = text
        elif topic == TOPIC_ERROR:
            try:
                data = json.loads(payload)
            except (ValueError, UnicodeDecodeError):
                data = None
            error = data.get("error") if isinstance(data, dict) else None
            self.last_error = error[:40] if isinstance(error, str) else "unreadable error message"
            log.warning("fan: node reported %s", self.last_error)

    # ---- status for read_sensors() ------------------------------------------
    def status(self, fake_rpm=0):
        """Fields added to each sensor reading. With the stub link, fan_rpm is
        `fake_rpm`; with the node it's the node's own tach reading, and 0 if
        the node is offline or quiet (it turns the fans off when it loses us)."""
        if getattr(self.link, "is_stub", False):
            return {"fan_rpm": fake_rpm, "fan_node": "stub"}
        with self._lock:
            state, at = self.node_state, self._state_at
        fresh = self.node != "offline" and state is not None and self.clock() - at <= STATE_FRESH_S
        return {"fan_rpm": state["fan_rpm"] if fresh else 0, "fan_node": self.node}


def _bench_test(argv):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    pct = int(argv[1]) if len(argv) > 1 else 50
    seconds = float(argv[2]) if len(argv) > 2 else 10
    controller = FanController()
    end = time.monotonic() + seconds
    try:
        while time.monotonic() < end:
            controller.set_speed(pct)  # resends, like the control loop
            print(controller.status(), "| node state:", controller.node_state)
            time.sleep(2)
    finally:
        controller.close()


if __name__ == "__main__":
    _bench_test(sys.argv)
