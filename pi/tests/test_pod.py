"""Tests for the Pi side. Run from the repo root:

    python3 -m unittest discover -s pi/tests -v

Covers the safety rules (heater/AC exclusion, junk values, one atomizer at
a time), the scent hub (commands, message validation, verify), settings
validation and history, and the web server's protections. The MQTT
end-to-end test runs only where mosquitto and paho-mqtt are installed.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hardware  # noqa: E402
import scent  # noqa: E402
from tools import record  # noqa: E402
from store import Store, ValidationError  # noqa: E402
from web import EventHub, start_server  # noqa: E402


class FakeLink:
    """Stands in for MQTT: records what the hub sends, delivers node messages."""

    def __init__(self):
        self.sent, self.closed, self.on_message, self.connected = [], False, None, True

    def start(self, on_message):
        self.on_message = on_message

    def publish(self, topic, payload, retain=False):
        if self.connected:  # like MqttLink: dropped, not queued, while offline
            self.sent.append((topic.rsplit("/", 1)[-1], payload, retain))
        return self.connected

    def close(self):
        self.closed = True

    def deliver(self, leaf, payload):
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.on_message(scent.TOPIC.format(leaf), raw)

    def cmds(self):
        return [p for leaf, p, _ in self.sent if leaf == "cmd"]


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def detect(gas=70.0, probs=(0.05, 0.9, 0.05, 0.0), atomizer=0, duty=75):
    return {"t_c": 24.0, "rh": 40.0, "p_hpa": 1010.0, "gas_ohm": [gas] * 10,
            "probs": list(probs), "atomizer": atomizer, "duty": duty}


class HardwareTests(unittest.TestCase):
    def setUp(self):
        hardware.setup()

    def tearDown(self):
        hardware.cleanup()

    def test_to_pct_rejects_junk(self):
        cases = [(50, 50), (150, 100), (-5, 0), (42.9, 42), (None, 0), ("50", 0),
                 (True, 0), (float("nan"), 0), (float("inf"), 0)]
        for value, want in cases:
            self.assertEqual(hardware.to_pct(value), want, value)

    def test_heater_and_ac_never_together(self):
        hardware.apply_settings({"heater_on": True, "ac_on": True})
        self.assertFalse(hardware.state["heater_running"])
        self.assertFalse(hardware.state["ac_running"])

    def test_junk_settings_mean_off(self):
        hardware.apply_settings({"heater_on": "yes", "fan_speed_pct": "x",
                                 "selected_scent": 7, "scent_intensity_pct": None})
        self.assertFalse(hardware.state["heater_running"])
        self.assertEqual(hardware.state["fan_pct"], 0)
        self.assertEqual(hardware.scent_hub.active, "none")

    def test_cleanup_turns_everything_off(self):
        hardware.apply_settings({"heater_on": True, "fan_speed_pct": 40,
                                 "selected_scent": "pine", "scent_intensity_pct": 70})
        hardware.cleanup()
        self.assertFalse(hardware.state["heater_running"])
        self.assertEqual(hardware.state["fan_pct"], 0)
        self.assertEqual(hardware.scent_hub.active, "none")

    def test_readings_come_from_the_node(self):
        link, clock = FakeLink(), FakeClock()
        hardware.scent_hub = scent.ScentHub(link, clock)
        link.deliver("telemetry", {"t_c": 25.0, "rh": 41.5, "p_hpa": 1012.3, "iaq": 57.4,
                                   "iaq_acc": 3, "eco2_ppm": 612.2, "bvoc_ppm": 0.87})
        r = hardware.read_sensors()
        self.assertEqual(r["actual_temp_f"], 77.0)
        self.assertEqual(r["actual_humidity_pct"], 41.5)
        self.assertEqual((r["iaq"], r["iaq_accuracy"], r["eco2_ppm"]), (57.0, 3, 612.0))

        # A real node that went quiet: no numbers rather than fake ones.
        clock.t += scent.TELEMETRY_FRESH_S + 1
        r = hardware.read_sensors()
        self.assertIsNone(r["actual_temp_f"])
        self.assertIsNone(r["iaq"])


class ScentHubTests(unittest.TestCase):
    def setUp(self):
        self.link, self.clock = FakeLink(), FakeClock()
        self.hub = scent.ScentHub(self.link, self.clock)

    def test_boots_off(self):
        self.assertEqual(self.link.cmds(), [{"atomizer": -1}])

    def test_one_atomizer_at_a_time_and_junk_means_off(self):
        self.hub.apply("lavender", 60)
        self.assertEqual(self.link.cmds()[-1], {"atomizer": scent.SCENT_ATOMIZERS["lavender"],
                                                "duty": 60, "on_s": scent.MAX_ON_S})
        self.hub.apply("pine", 130)  # clamped
        self.assertEqual(self.link.cmds()[-1]["atomizer"], scent.SCENT_ATOMIZERS["pine"])
        self.assertEqual(self.link.cmds()[-1]["duty"], 100)
        for off in [("pine", 0), ("bogus", 80), ("none", 80)]:
            self.hub.apply("lavender", 50)
            self.hub.apply(*off)
            self.assertEqual(self.link.cmds()[-1], {"atomizer": -1}, off)
        for cmd in self.link.cmds():
            self.assertIsInstance(cmd["atomizer"], int)  # never a list of several
            self.assertLessEqual(cmd.get("on_s", 0), scent.MAX_ON_S)

    def test_resends_to_keep_running_but_not_every_tick(self):
        self.hub.apply("lavender", 60)
        n = len(self.link.cmds())
        self.clock.t += scent.CMD_REFRESH_S - 1
        self.hub.apply("lavender", 60)
        self.assertEqual(len(self.link.cmds()), n)
        self.clock.t += 1
        self.hub.apply("lavender", 60)
        self.assertEqual(len(self.link.cmds()), n + 1)

    def test_retries_next_tick_when_not_connected_yet(self):
        link, clock = FakeLink(), FakeClock()
        link.connected = False  # boot: MQTT still connecting
        hub = scent.ScentHub(link, clock)
        hub.apply("lavender", 60)
        self.assertEqual(link.cmds(), [])
        link.connected = True
        clock.t += 2  # one control tick, well under CMD_REFRESH_S
        hub.apply("lavender", 60)
        self.assertEqual(link.cmds(), [{"atomizer": 0, "duty": 60, "on_s": scent.MAX_ON_S}])

    def test_close_turns_off_and_disconnects(self):
        self.hub.apply("pine", 40)
        self.hub.close()
        self.assertEqual(self.link.cmds()[-1], {"atomizer": -1})
        self.assertTrue(self.link.closed)

    def test_ignores_junk_from_the_network(self):
        bad_telemetry = [b"not json", b"\xff", b"[1, 2]", b"NaN", {"t_c": "hot"}, {"t_c": True}]
        for payload in bad_telemetry:
            self.link.deliver("telemetry", payload)
        env = self.hub.environment()
        self.assertTrue(env is None or env["t_c"] is None)

        bad_detect = [detect(gas=-1), detect(probs=(2, 0, 0, 0)), detect(probs=(1, 0)),
                      {**detect(), "gas_ohm": []}, {**detect(), "gas_ohm": [1.0] * 11},
                      {**detect(), "gas_ohm": "lots"}, {**detect(), "probs": [True, 0, 0, 0]}]
        for payload in bad_detect:
            self.assertIsNone(scent.parse_detect(payload), payload)
        self.assertIsNone(scent.parse_detect(scent.decode(b"[NaN]")))
        self.assertIsNotNone(scent.parse_detect(detect()))

    def test_absurd_messages_dont_raise(self):
        # Either would escape paho's callback and kill its network thread.
        self.link.deliver("telemetry", b'{"t_c": 1' + b"0" * 400 + b"}")
        self.assertIsNone(self.hub.environment()["t_c"])
        self.link.deliver("detect", b"[" * 100_000 + b"]" * 100_000)
        self.assertIsNone(scent.parse_detect({**detect(), "gas_ohm": [10 ** 400] * 10}))

    def test_learns_baseline_only_from_settled_clean_air(self):
        self.link.deliver("detect", detect(gas=100, atomizer=-1))  # not settled yet
        self.assertIsNone(self.hub._baseline)
        self.clock.t += scent.SETTLE_S
        self.link.deliver("detect", detect(gas=50, atomizer=0))  # node still misting
        self.assertIsNone(self.hub._baseline)
        self.link.deliver("detect", detect(gas=100, atomizer=-1))
        self.assertEqual(self.hub._baseline, [100.0] * 10)

    def test_partial_scan_keeps_the_baseline(self):
        self.clock.t += scent.SETTLE_S
        self.link.deliver("detect", detect(gas=100, atomizer=-1))
        short = {**detect(gas=40, atomizer=-1), "gas_ohm": [40.0] * 9}
        self.link.deliver("detect", short)
        self.assertEqual(self.hub._baseline, [100.0] * 10)
        for _ in range(scent.BASELINE_RESET_AFTER - 1):  # heater profile changed
            self.link.deliver("detect", short)
        self.assertEqual(self.hub._baseline, [40.0] * 9)

    def test_verify_flow(self):
        self.link.deliver("status", b"online")
        self.clock.t += scent.SETTLE_S
        self.link.deliver("detect", detect(gas=100, atomizer=-1))  # clean-air baseline

        self.hub.apply("lavender", 75)  # expects a response of 0.3
        self.assertEqual(self.hub.check()["status"], "pending")
        self.link.deliver("detect", detect(gas=70))  # too soon to judge
        self.assertEqual(self.hub.check()["status"], "pending")

        self.clock.t += scent.SETTLE_S
        self.link.deliver("detect", detect(gas=70))
        self.assertEqual(self.hub.check()["status"], "pass")
        leaf, published, retain = self.link.sent[-1]
        self.assertEqual((leaf, published["status"], retain), ("verify", "pass", True))

        self.link.deliver("detect", detect(gas=70, probs=(0.1, 0.1, 0.8, 0)))
        self.assertIn("smells like pine", self.hub.check()["reason"])

        self.hub.apply("none", 0)
        self.assertIsNone(self.hub.check())
        # The retained result is replaced, so it can't outlive the scent.
        self.assertEqual(self.link.sent[-1], ("verify", {"status": "off"}, True))

    def test_change_replaces_the_retained_result(self):
        self.hub.apply("lavender", 50)
        self.hub.apply("lavender", 90)
        leaf, published, retain = self.link.sent[-1]
        self.assertEqual((leaf, published["status"], published["duty"], retain),
                         ("verify", "pending", 90, True))

    def test_stub_has_no_check(self):
        hub = scent.ScentHub(scent.StubLink(), FakeClock())  # laptop: no node
        hub.apply("lavender", 50)
        self.assertIsNone(hub.check())

    def test_fails_when_node_isnt_running_the_atomizer(self):
        # e.g. pins still -1 on the node, so it rejected the command
        self.link.deliver("status", b"online")
        self.hub.apply("pine", 50)
        self.clock.t += scent.SETTLE_S
        self.link.deliver("detect", detect(probs=(0.1, 0.1, 0.8, 0), atomizer=-1))
        self.assertEqual(self.hub.check()["status"], "fail")
        self.assertIn("isn't running the atomizer", self.hub.check()["reason"])

    def test_check_reports_offline_and_silent_node(self):
        self.hub.apply("lavender", 50)
        self.assertEqual(self.hub.check()["reason"], "scent node offline")
        self.link.deliver("status", b"online")
        self.assertEqual(self.hub.check()["status"], "pending")
        self.clock.t += scent.SETTLE_S + scent.DETECT_FRESH_S
        self.assertEqual(self.hub.check()["reason"], "no scan data from the node")
        self.link.deliver("status", b"offline")
        self.assertEqual(self.hub.check()["reason"], "scent node offline")

    def test_broken_mqtt_keeps_the_agent_running(self):
        class Broken(FakeLink):
            def start(self, on_message):
                raise ImportError("No module named 'paho'")

        with self.assertLogs("xrpod.scent", "ERROR"):
            hub = scent.ScentHub(Broken(), FakeClock())
        self.assertFalse(hub.is_stub)  # a real node was configured: no fake data
        hub.apply("lavender", 50)  # doesn't raise
        hub.close()


class MqttLinkTests(unittest.TestCase):
    """MqttLink against a stand-in paho client (no broker needed)."""

    class Client:
        def __init__(self, connected):
            self.connected, self.published, self.stopped = connected, [], False

        def is_connected(self):
            return self.connected

        def publish(self, *args, **kwargs):
            self.published.append(args)
            return self

        def wait_for_publish(self, timeout):
            raise RuntimeError("The client is not currently connected.")

        def disconnect(self):
            pass

        def loop_stop(self):
            self.stopped = True

    def test_drops_instead_of_queuing_while_disconnected(self):
        link = scent.MqttLink("broker")
        link.client = self.Client(connected=False)
        link.publish("t", {"atomizer": 0})
        self.assertEqual(link.client.published, [])
        link.client.connected = True
        link.publish("t", {"atomizer": -1})
        self.assertEqual(len(link.client.published), 1)

    def test_close_survives_a_connection_drop(self):
        link = scent.MqttLink("broker")
        link.client = self.Client(connected=True)
        link.publish("t", {"atomizer": -1})
        with self.assertLogs("xrpod.scent", "WARNING"):
            link.close()  # wait_for_publish raises; close must still finish
        self.assertTrue(link.client.stopped)


class VerifyTests(unittest.TestCase):
    BASE = [100.0] * 10

    def check(self, gas=70.0, probs=(0.05, 0.9, 0.05, 0), duty=75, scent_name="lavender",
              baseline=BASE):
        return scent.verify(scent_name, duty, detect(gas, probs), baseline)

    def test_right_scent_right_strength_passes(self):
        r = self.check()
        self.assertEqual(r["status"], "pass", r)
        self.assertEqual((r["response"], r["expected"]), (0.3, 0.3))

    def test_failures(self):
        cases = {
            "smells like pine": self.check(probs=(0.1, 0.1, 0.8, 0)),
            "too weak": self.check(gas=95),
            "too strong": self.check(gas=20),
            "no clean-air baseline": self.check(baseline=None),
            "isn't a class": self.check(scent_name="ocean"),
        }
        for reason, r in cases.items():
            self.assertEqual(r["status"], "fail", reason)
            self.assertIn(reason, r["reason"])

    def test_classifier_warming_up_is_pending(self):
        self.assertEqual(self.check(probs=(0, 0, 0, 0))["status"], "pending")

    def test_baseline_follows_slowly(self):
        b = scent.update_baseline(None, [100.0, 200.0])
        self.assertEqual(b, [100.0, 200.0])
        b = scent.update_baseline(b, [0.0, 200.0])
        self.assertAlmostEqual(b[0], 100 * (1 - scent.BASELINE_ALPHA))
        self.assertEqual(scent.update_baseline(b, [1.0]), [1.0])  # profile changed


class RecordTests(unittest.TestCase):
    def test_row_matches_columns(self):
        when = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
        row = record.row("xrpod/scent/scent1/detect", scent.parse_detect(detect()), "lavender", when)
        self.assertEqual(len(row), len(record.COLUMNS))
        by_col = dict(zip(record.COLUMNS, row))
        self.assertEqual((by_col["node"], by_col["label"], by_col["gas_ohm_9"], by_col["prob_1"]),
                         ("scent1", "lavender", 70.0, 0.9))
        self.assertEqual(by_col["timestamp"], "2026-10-28T12:00:00+00:00")

    def test_short_heater_profile_pads_columns(self):
        d = scent.parse_detect({**detect(), "gas_ohm": [5.0, 6.0]})
        row = dict(zip(record.COLUMNS, record.row("xrpod/scent/n/detect", d, "x", datetime.now())))
        self.assertEqual((row["gas_ohm_1"], row["gas_ohm_2"]), (6.0, ""))


def _paho_available():
    try:
        import paho.mqtt.client  # noqa: F401
    except ImportError:
        return False
    return True


@unittest.skipUnless(shutil.which("mosquitto") and _paho_available(),
                     "needs mosquitto and paho-mqtt installed")
class MqttEndToEndTests(unittest.TestCase):
    """Real broker, real MqttLink, and a fake node speaking the contract."""

    def setUp(self):
        import paho.mqtt.client as mqtt

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.broker = subprocess.Popen(["mosquitto", "-p", str(self.port)],  # noqa: S603, S607
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.broker.wait, 5)
        self.addCleanup(self.broker.terminate)
        try:
            node = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="fake-node")
        except AttributeError:
            node = mqtt.Client(client_id="fake-node")
        self.cmds = []
        node.on_message = lambda c, u, msg: self.cmds.append(json.loads(msg.payload))
        self.wait_for(lambda: node.connect("127.0.0.1", self.port) == 0, ignore=OSError)
        node.subscribe(scent.TOPIC.format("cmd"), qos=1)
        node.loop_start()
        self.addCleanup(node.disconnect)
        self.addCleanup(node.loop_stop)
        self.node = node

    def wait_for(self, cond, timeout=5, ignore=()):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                if cond():
                    return
            except ignore:
                pass
            time.sleep(0.05)
        self.fail("timed out")

    def test_hub_and_node_talk(self):
        topics = [scent.TOPIC.format(t) for t in ("status", "telemetry", "detect")]
        hub = scent.ScentHub(scent.MqttLink("127.0.0.1", self.port, topics=topics))
        self.wait_for(lambda: hub.link.client.is_connected())
        time.sleep(0.2)  # let the subscriptions land
        self.node.publish(scent.TOPIC.format("status"), "online", qos=1, retain=True)
        self.node.publish(scent.TOPIC.format("telemetry"), json.dumps({"t_c": 22.0, "iaq": 40}), qos=1)
        self.wait_for(lambda: hub.environment() is not None)
        self.assertEqual(hub.environment()["t_c"], 22.0)

        hub.apply("pine", 40)
        self.wait_for(lambda: self.cmds and self.cmds[-1].get("atomizer") == 1)
        self.assertEqual(self.cmds[-1], {"atomizer": 1, "duty": 40, "on_s": scent.MAX_ON_S})
        self.assertEqual(hub.check()["status"], "pending")

        # Stopping the agent must get "off" to the node before disconnecting.
        hub.close()
        self.wait_for(lambda: self.cmds[-1] == {"atomizer": -1})


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "t.db"))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_defaults(self):
        s = self.store.get_settings()
        self.assertEqual(s["target_temp_f"], 72)
        self.assertFalse(s["heater_on"])

    def test_turning_one_on_turns_the_other_off(self):
        self.store.update_settings({"heater_on": True})
        s, rows = self.store.update_settings({"ac_on": True})
        self.assertTrue(s["ac_on"])
        self.assertFalse(s["heater_on"])
        self.assertEqual({r["field_name"] for r in rows}, {"ac_on", "heater_on"})

    def test_rejects_bad_values(self):
        bad = [{"heater_on": True, "ac_on": True}, {"fan_speed_pct": 150},
               {"fan_speed_pct": 40.5}, {"fan_speed_pct": True}, {"heater_on": 1},
               {"selected_scent": "bacon"}, {"target_temp_f": float("nan")},
               {"evil": 1}, {}, []]
        for patch in bad:
            with self.assertRaises(ValidationError, msg=patch):
                self.store.update_settings(patch)
        self.assertEqual(self.store.get_history(), [])

    def test_history_logs_each_field_and_skips_no_ops(self):
        self.store.update_settings({"fan_speed_pct": 40, "selected_scent": "pine"}, "1.2.3.4")
        _, rows = self.store.update_settings({"fan_speed_pct": 40})
        self.assertEqual(rows, [])
        hist = self.store.get_history()
        self.assertEqual(len(hist), 2)
        by_field = {r["field_name"]: r for r in hist}
        self.assertEqual(by_field["fan_speed_pct"]["old_value"], "0")
        self.assertEqual(by_field["fan_speed_pct"]["new_value"], "40")
        self.assertEqual(by_field["selected_scent"]["changed_by"], "1.2.3.4")

    def test_settings_survive_restart(self):
        self.store.update_settings({"selected_scent": "lavender"})
        self.store.close()
        self.store = Store(os.path.join(self.tmp.name, "t.db"))
        self.assertEqual(self.store.get_settings()["selected_scent"], "lavender")

    def test_removed_scent_falls_back_to_none(self):
        # A database saved before the scent list was cut to the node's two.
        self.store._db.execute("""UPDATE settings SET data = '{"selected_scent": "ocean"}'""")
        self.store._db.commit()
        self.store.close()
        self.store = Store(os.path.join(self.tmp.name, "t.db"))
        self.assertEqual(self.store.get_settings()["selected_scent"], "none")

    def test_readings(self):
        self.assertIsNone(self.store.get_latest_reading())
        self.store.add_reading({"actual_temp_f": 70.0})
        latest = self.store.add_reading({"actual_temp_f": 71.0})
        self.assertEqual(self.store.get_latest_reading(), latest)


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        static = os.path.join(cls.tmp.name, "dist")
        os.makedirs(static)
        with open(os.path.join(static, "index.html"), "w") as f:
            f.write("<!doctype html><title>HUD</title>")
        with open(os.path.join(cls.tmp.name, "secret.txt"), "w") as f:
            f.write("do not serve")
        cls.store = Store(os.path.join(cls.tmp.name, "t.db"))
        cls.changed = threading.Event()
        cls.server = start_server(cls.store, EventHub(), "127.0.0.1", 0, static,
                                  on_settings_changed=cls.changed.set)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.store.close()
        cls.tmp.cleanup()

    def request(self, method, path, body=None, headers=None):
        data = body.encode() if isinstance(body, str) else body
        req = urllib.request.Request(self.base + path, data=data, method=method,  # noqa: S310
                                     headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as err:
            return err.code, err.read().decode()

    def patch(self, body, **headers):
        return self.request("PATCH", "/api/settings", body,
                            {"Content-Type": "application/json", **headers})

    def test_patch_saves_and_wakes_control_loop(self):
        self.changed.clear()
        status, body = self.patch(json.dumps({"fan_speed_pct": 30}))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["fan_speed_pct"], 30)
        self.assertTrue(self.changed.is_set())

    def test_invalid_patch_is_400(self):
        self.assertEqual(self.patch(json.dumps({"fan_speed_pct": 500}))[0], 400)
        self.assertEqual(self.patch("not json")[0], 400)

    def test_blocks_other_websites(self):
        status, _ = self.patch(json.dumps({"fan_speed_pct": 10}), Origin="http://evil.example")
        self.assertEqual(status, 403)
        # Forms can't send JSON, so a form-style post is refused too.
        status, _ = self.request("PATCH", "/api/settings", "fan_speed_pct=10",
                                 {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(status, 415)

    def test_allows_same_origin_and_non_browser_clients(self):
        host = self.base.split("//")[1]
        self.assertEqual(self.patch(json.dumps({"fan_speed_pct": 11}), Origin=self.base)[0], 200)
        self.assertEqual(self.patch(json.dumps({"fan_speed_pct": 12}), Host=host)[0], 200)

    def test_rejects_oversized_body(self):
        status, _ = self.patch(json.dumps({"fan_speed_pct": 1, "pad": "x" * 10000}))
        self.assertEqual(status, 400)

    def test_static_files_and_no_path_traversal(self):
        self.assertEqual(self.request("GET", "/")[0], 200)
        self.assertIn("HUD", self.request("GET", "/some/route")[1])
        for path in ["/../secret.txt", "/%2e%2e/secret.txt"]:
            self.assertNotIn("do not serve", self.request("GET", path)[1], path)

    def test_read_endpoints(self):
        self.assertEqual(self.request("GET", "/api/settings")[0], 200)
        self.assertEqual(self.request("GET", "/api/history?limit=5")[0], 200)
        self.assertEqual(self.request("GET", "/api/history?limit=abc")[0], 400)
        self.assertEqual(self.request("GET", "/api/readings/latest")[0], 200)
        self.assertEqual(self.request("GET", "/api/nope")[0], 404)


if __name__ == "__main__":
    unittest.main()
