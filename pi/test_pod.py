"""Tests for the Pi side. Run from the repo root:

    python3 -m unittest discover -s pi -v

Covers the safety rules (heater/AC exclusion, junk values, one scent at a
time), settings validation and history, and the web server's protections.
"""

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))

import hardware  # noqa: E402
import scent  # noqa: E402
from store import Store, ValidationError  # noqa: E402
from web import EventHub, start_server  # noqa: E402


class RecordingBackend:
    def __init__(self):
        self.on, self.duty, self.max_on = set(), None, 0

    def setup(self, *args):
        pass

    def set_output(self, pin, on):
        (self.on.add if on else self.on.discard)(pin)
        self.max_on = max(self.max_on, len(self.on))

    def set_pwm(self, duty):
        self.duty = duty

    def close(self):
        pass


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
        self.assertEqual(hardware.scent_machine.active, "none")

    def test_cleanup_turns_everything_off(self):
        hardware.apply_settings({"heater_on": True, "fan_speed_pct": 40,
                                 "selected_scent": "pine", "scent_intensity_pct": 70})
        hardware.cleanup()
        self.assertFalse(hardware.state["heater_running"])
        self.assertEqual(hardware.state["fan_pct"], 0)
        self.assertEqual(hardware.scent_machine.active, "none")


class ScentTests(unittest.TestCase):
    def test_one_cartridge_at_a_time(self):
        rec = RecordingBackend()
        c = scent.ScentController(rec)
        c.apply("lavender", 60)
        self.assertEqual(rec.on, {scent.CARTRIDGE_PINS["lavender"]})
        self.assertEqual(rec.duty, 60)
        c.apply("pine", 30)
        self.assertEqual(rec.on, {scent.CARTRIDGE_PINS["pine"]})
        for off in [("pine", 0), ("bogus", 80), ("none", 80)]:
            c.apply(*off)
            self.assertEqual(rec.on, set(), off)
        self.assertEqual(rec.max_on, 1)


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
        self.store.update_settings({"selected_scent": "ocean"})
        self.store.close()
        self.store = Store(os.path.join(self.tmp.name, "t.db"))
        self.assertEqual(self.store.get_settings()["selected_scent"], "ocean")

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
