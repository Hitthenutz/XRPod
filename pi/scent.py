"""
XRPod scent hub: the Pi side of the ESP32 scent / IAQ node
(subsystems/iaq/firmware/scent-node). Runs inside agent.py.

The node is thin: it reports what its two BME688s see and runs an atomizer
only when told. This module makes the decisions:
  * turns the HUD's scent setting into atomizer commands over MQTT, one
    atomizer at a time, re-sent every CMD_REFRESH_S. Each command expires on
    the node after MAX_ON_S, so a dead Pi can't leave a scent running,
  * checks that the right scent arrived at the right strength and publishes
    pass/fail to xrpod/scent/<node>/verify (and to the HUD via readings),
  * hands the IAQ sensor's telemetry (temp, humidity, IAQ, eCO2, bVOC) to
    hardware.read_sensors().
MQTT topics and the verify method: subsystems/iaq/docs/DESIGN.md.

Without MQTT_HOST set it uses a stub link that only logs, so the agent runs
on any machine. On the Pi it needs python3-paho-mqtt (see README).
"""

import json
import logging
import math
import os
import threading
import time

log = logging.getLogger("xrpod.scent")

# ---------NODE + SCENTS---------
NODE = "scent1"  # NODE_ID in subsystems/iaq/firmware/scent-node/include/config.h
TOPIC = "xrpod/scent/" + NODE + "/{}"

# Scent -> atomizer on the node. Keys must match SCENTS in store.py.
# ---------MISSING: FINAL SCENT NAMES (placeholders)---------
SCENT_ATOMIZERS = {"lavender": 0, "pine": 1}

# What BSEC_OUTPUT_GAS_ESTIMATE_1..4 mean, in the AI-Studio export's order.
# None = unused slot.
# ---------MISSING: AI-STUDIO CLASS ORDER---------
CLASS_NAMES = ("clean_air", "lavender", "pine", None)

# ---------TIMING---------
MAX_ON_S = 30  # same as MAX_ON_S in config.h; the node enforces it
CMD_REFRESH_S = 5  # re-send the running command this often
TELEMETRY_FRESH_S = 15  # the node sends every 3 s
DETECT_FRESH_S = 60  # one heater scan takes ~18 s
NEVER = float("-inf")

# ---------VERIFY---------
# ---------MISSING: CALIBRATION (record with pi/tools/record.py)---------
SETTLE_S = 60  # wait this long after a change before judging
PASS_PROB = 0.6  # class probability needed to call it the right scent
INTENSITY_PER_DUTY = 0.004  # expected gas response per duty % (0.4 at 100 %)
STRENGTH_TOL = 0.15  # allowed +/- around the expected response
BASELINE_ALPHA = 0.1  # how fast the clean-air baseline follows the room
BASELINE_RESET_AFTER = 3  # scans in a row with a new step count reset it


# ---------MESSAGE VALIDATION (never trust the network)---------
def _number(value):
    """A finite float, or None. Rejects bools, strings, NaN and inf."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        value = float(value)
    except OverflowError:  # a JSON int too big for a float
        return None
    return value if math.isfinite(value) else None


def _atomizer(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def parse_telemetry(data):
    """IAQ sensor reading from the node, or None if it isn't one."""
    if not isinstance(data, dict):
        return None
    out = {k: _number(data.get(k)) for k in
           ("t_c", "rh", "p_hpa", "iaq", "eco2_ppm", "bvoc_ppm")}
    acc = _atomizer(data.get("iaq_acc"))
    out["iaq_acc"] = acc if acc in (0, 1, 2, 3) else None
    out["atomizer"] = _atomizer(data.get("atomizer"))
    return out


def parse_detect(data):
    """Scan sensor result from the node, or None if it isn't a valid one."""
    if not isinstance(data, dict):
        return None
    gas, probs = data.get("gas_ohm"), data.get("probs")
    if not isinstance(gas, list) or not 1 <= len(gas) <= 10:
        return None
    if not isinstance(probs, list) or len(probs) != len(CLASS_NAMES):
        return None
    gas = [_number(g) for g in gas]
    probs = [_number(p) for p in probs]
    if any(g is None or g <= 0 for g in gas) or any(p is None or not 0 <= p <= 1 for p in probs):
        return None
    out = {k: _number(data.get(k)) for k in ("t_c", "rh", "p_hpa")}
    out.update(gas_ohm=gas, probs=probs, atomizer=_atomizer(data.get("atomizer")),
               duty=_atomizer(data.get("duty")))
    return out


# ---------GAS RESPONSE + VERIFY---------
def update_baseline(baseline, gas):
    """Clean-air gas resistance per heater step, as a slow moving average."""
    if baseline is None or len(baseline) != len(gas):
        return list(gas)
    return [b + BASELINE_ALPHA * (g - b) for b, g in zip(baseline, gas)]


def gas_response(gas, baseline):
    """How far the gas resistance dropped below clean air: 0 = clean air,
    toward 1 = strong. Scent VOCs lower a BME688's resistance. None if
    there's no matching baseline yet."""
    if baseline is None or len(baseline) != len(gas):
        return None
    return 1 - sum(g / b for g, b in zip(gas, baseline)) / len(gas)


def verify(scent, duty, detect, baseline):
    """Did `scent` arrive at about the strength `duty` should give?
    Returns {"status": "pass" | "fail" | "pending", "reason": ..., ...}."""
    expected = INTENSITY_PER_DUTY * duty
    response = gas_response(detect["gas_ohm"], baseline)
    probs = detect["probs"]
    prob = probs[CLASS_NAMES.index(scent)] if scent in CLASS_NAMES else None
    result = {
        "scent": scent,
        "duty": duty,
        "prob": None if prob is None else round(prob, 3),
        "response": None if response is None else round(response, 3),
        "expected": round(expected, 3),
    }

    if not any(probs):
        return {**result, "status": "pending", "reason": "classifier still collecting data"}
    reasons = []
    if prob is None:
        reasons.append(f"{scent} isn't a class in the AI-Studio config")
    elif prob < PASS_PROB:
        top = max(range(len(probs)), key=probs.__getitem__)
        reasons.append(f"smells like {CLASS_NAMES[top] or 'an unused class'}, not {scent}")
    if response is None:
        reasons.append("no clean-air baseline yet")
    elif response < expected - STRENGTH_TOL:
        reasons.append("too weak")
    elif response > expected + STRENGTH_TOL:
        reasons.append("too strong")
    if reasons:
        return {**result, "status": "fail", "reason": "; ".join(reasons)}
    return {**result, "status": "pass", "reason": ""}


# ---------MQTT LINKS---------
class StubLink:
    """Logs instead of talking MQTT. Used when MQTT_HOST isn't set."""

    def start(self, on_message):
        log.info("scent: STUB link (set MQTT_HOST to talk to the scent node)")

    def publish(self, topic, payload, retain=False):
        log.debug("scent: would publish %s %s", topic, payload)
        return True

    def close(self):
        pass


class MqttLink:
    """paho-mqtt client that reconnects by itself in a background thread."""

    def __init__(self, host, port=1883, user=None, password=None, topics=()):
        self.host, self.port, self.user, self.password = host, port, user, password
        self.topics = list(topics)
        self.client = None
        self._last = None

    def start(self, on_message):
        import paho.mqtt.client as mqtt  # python3-paho-mqtt on the Pi

        try:  # paho 2.x
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"xrpod-{os.getpid()}")
        except AttributeError:  # paho 1.x, as shipped by Raspberry Pi OS
            client = mqtt.Client(client_id=f"xrpod-{os.getpid()}")
        if self.user:
            client.username_pw_set(self.user, self.password)

        # Re-subscribe on every (re)connect. paho 1.x passes rc as an int,
        # 2.x as a ReasonCode (which compares to ints); both put it 4th.
        def on_connect(c, userdata, flags, rc, *_):
            if rc != 0:
                log.error("scent: MQTT broker refused the connection (%s); check MQTT_USER/MQTT_PASS", rc)
                return
            for topic in self.topics:
                c.subscribe(topic, qos=1)

        client.on_connect = on_connect
        # An exception here would kill paho's network thread, and with it
        # every command and reading, so one bad message must never escape.
        def on_msg(c, userdata, msg):
            try:
                on_message(msg.topic, msg.payload)
            except Exception:
                log.exception("scent: error handling a message on %s", msg.topic)

        client.on_message = on_msg
        client.reconnect_delay_set(1, 30)
        client.connect_async(self.host, self.port, keepalive=30)
        client.loop_start()
        self.client = client
        log.info("scent: MQTT broker %s:%s", self.host, self.port)

    def publish(self, topic, payload, retain=False):
        """Returns False if dropped. While disconnected we drop rather than
        queue: paho would otherwise pile up commands without limit and
        replay stale ones on reconnect. The hub retries the current state,
        and the node turns itself off while it can't hear us."""
        if not self.client.is_connected():
            return False
        self._last = self.client.publish(topic, json.dumps(payload), qos=1, retain=retain)
        return True

    def close(self):
        try:
            if self._last is not None and self.client.is_connected():
                self._last.wait_for_publish(timeout=2)  # let the final "off" go out
        except (RuntimeError, ValueError):  # connection dropped mid-wait
            log.warning("scent: couldn't confirm the final 'off' reached the broker")
        self.client.disconnect()
        self.client.loop_stop()


def make_link(topics):
    host = os.environ.get("MQTT_HOST")
    if not host:
        return StubLink()
    return MqttLink(host, int(os.environ.get("MQTT_PORT", "1883")),
                    os.environ.get("MQTT_USER"), os.environ.get("MQTT_PASS"), topics)


def decode(payload):
    """JSON from an MQTT payload, or None."""
    try:
        return json.loads(payload)
    except (ValueError, RecursionError):  # bad JSON or UTF-8, absurd nesting
        return None


# ---------HUB---------
class ScentHub:
    """Keeps the node in the requested state and checks the result."""

    def __init__(self, link=None, clock=time.monotonic):
        topics = [TOPIC.format(leaf) for leaf in ("status", "telemetry", "detect")]
        self.link = link or make_link(topics)
        self.clock = clock
        self._lock = threading.Lock()
        self.active, self.intensity = "none", 0
        self._changed_at = clock()
        self._sent_at = NEVER
        self._online = False
        self._telemetry = None  # (time, reading)
        self._detect_at = None
        self._baseline = None
        self._baseline_misses = 0
        self._check = None
        # is_stub = no node configured (laptop testing), so fake data is OK.
        self.is_stub = isinstance(self.link, StubLink)
        try:
            self.link.start(self._on_message)
        except Exception:  # e.g. python3-paho-mqtt missing: keep the HUD up
            log.exception("scent: can't start MQTT; scent node disabled")
            self.link = StubLink()
        self.off()

    # ------------------------------------------------------------ commands
    def apply(self, scent, intensity_pct):
        """Run `scent` at `intensity_pct` (0-100). Unknown scent, "none" or
        0 % all mean off. Call every control tick; it re-sends as needed."""
        intensity = max(0, min(100, int(intensity_pct)))
        if scent not in SCENT_ATOMIZERS or intensity == 0:
            self.off()
            return
        now = self.clock()
        with self._lock:
            changed = (scent, intensity) != (self.active, self.intensity)
            if changed:
                if scent != self.active:
                    log.info("scent: %s at %s%%", scent, intensity)
                self.active, self.intensity = scent, intensity
                self._changed_at = now
                self._check = pending = {"status": "pending", "reason": "settling",
                                         "scent": scent, "duty": intensity}
            if not changed and now - self._sent_at < CMD_REFRESH_S:
                return
            self._sent_at = now
        # The node turns any other atomizer off first.
        self._send({"atomizer": SCENT_ATOMIZERS[scent], "duty": intensity, "on_s": MAX_ON_S})
        if changed:  # replace the retained result of the previous run
            self.link.publish(TOPIC.format("verify"), pending, retain=True)

    def off(self):
        now = self.clock()
        with self._lock:
            was_on = self.active != "none"
            if was_on:
                log.info("scent: off")
                self._changed_at = now
            if not was_on and now - self._sent_at < CMD_REFRESH_S:
                return
            self.active, self.intensity = "none", 0
            self._check = None
            self._sent_at = now
        self._send({"atomizer": -1})
        if was_on:  # so the retained result doesn't outlive the scent
            self.link.publish(TOPIC.format("verify"), {"status": "off"}, retain=True)

    def _send(self, cmd):
        # Not connected yet (e.g. at boot) or just dropped: retry next tick
        # instead of waiting a whole CMD_REFRESH_S.
        if self.link.publish(TOPIC.format("cmd"), cmd) is False:
            with self._lock:
                self._sent_at = NEVER

    def close(self):
        self.off()
        self.link.close()

    # -------------------------------------------------------- node -> hub
    def _on_message(self, topic, payload):
        leaf = topic.rsplit("/", 1)[-1]
        if leaf == "status":
            with self._lock:
                self._online = payload == b"online"
            return
        data = decode(payload)
        now = self.clock()
        if leaf == "telemetry":
            reading = parse_telemetry(data)
            if reading is None:
                log.warning("scent: ignoring bad telemetry")
                return
            with self._lock:
                self._telemetry = (now, reading)
        elif leaf == "detect":
            detect = parse_detect(data)
            if detect is None:
                log.warning("scent: ignoring bad detect message")
                return
            self._on_detect(now, detect)

    def _on_detect(self, now, detect):
        with self._lock:
            self._detect_at = now
            settled = now - self._changed_at >= SETTLE_S
            if not settled:
                return
            if self.active == "none":
                if detect["atomizer"] == -1:
                    self._learn_baseline(detect["gas_ohm"])
                return
            if detect["atomizer"] != SCENT_ATOMIZERS[self.active]:
                check = {"status": "fail", "scent": self.active, "duty": self.intensity,
                         "reason": "node isn't running the atomizer (pins set? see node log)"}
            else:
                check = verify(self.active, self.intensity, detect, self._baseline)
            if (self._check or {}).get("status") != check["status"]:
                log.info("scent check: %s %s", check["status"], check["reason"])
            self._check = check
        self.link.publish(TOPIC.format("verify"), check, retain=True)

    def _learn_baseline(self, gas):
        # One scan with a different step count is a partial scan; only a run
        # of them means the node's heater profile really changed.
        if self._baseline is not None and len(gas) != len(self._baseline):
            self._baseline_misses += 1
            if self._baseline_misses < BASELINE_RESET_AFTER:
                return
        self._baseline_misses = 0
        self._baseline = update_baseline(self._baseline, gas)

    # ---------------------------------------------------- for hardware.py
    def environment(self):
        """Latest IAQ sensor reading, or None if the node has gone quiet."""
        with self._lock:
            if self._telemetry and self.clock() - self._telemetry[0] <= TELEMETRY_FRESH_S:
                return dict(self._telemetry[1])
            return None

    def check(self):
        """Latest verify result for the running scent, or None when off."""
        with self._lock:
            if self.active == "none" or self.is_stub:  # stub: no node to check
                return None
            now = self.clock()
            if not self._online:
                return {"status": "fail", "reason": "scent node offline",
                        "scent": self.active, "duty": self.intensity}
            if now - self._changed_at >= SETTLE_S + DETECT_FRESH_S and (
                    self._detect_at is None or now - self._detect_at > DETECT_FRESH_S):
                return {"status": "fail", "reason": "no scan data from the node",
                        "scent": self.active, "duty": self.intensity}
            return dict(self._check)


def _bench_test(argv):
    """python3 scent.py lavender 60 [seconds]: run one scent, print checks."""
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(message)s")
    scent = argv[1] if len(argv) > 1 else "lavender"
    intensity = int(argv[2]) if len(argv) > 2 else 50
    seconds = float(argv[3]) if len(argv) > 3 else 10
    hub = ScentHub()
    try:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            hub.apply(scent, intensity)
            log.info("check: %s  env: %s", hub.check(), hub.environment())
            time.sleep(2)
    finally:
        hub.close()


if __name__ == "__main__":
    import sys

    _bench_test(sys.argv)
