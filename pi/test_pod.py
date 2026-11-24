"""Tests for the Pi side. Run from the repo root:

    python3 -m unittest discover -s pi -v

Covers the safety rules (heater/AC exclusion, junk values, scent and fan
commands and node reports), the MQTT client, settings validation and history, VR
state reports, and the web server's protections."""

import base64
import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))

import datalog  # noqa: E402
import fan  # noqa: E402
import hardware  # noqa: E402
import mqtt  # noqa: E402
import scent  # noqa: E402
import store as store_module  # noqa: E402
from store import Store, ValidationError  # noqa: E402
from vr import FRAME_STALE_SECONDS, MAX_FRAME_BYTES, STALE_SECONDS, VrFrame, VrState  # noqa: E402
from web import EventHub, start_server  # noqa: E402

GOOD_VR = {"session_id": "test1", "seq": 2, "environment": "forest",
           "zone_id": "clearing-wind", "zone_type": "windy", "zone_tracking": True,
           "reason": "zone_entered"}

# Smallest thing that looks like a JPEG: start and end markers around data.
FAKE_JPEG = b"\xff\xd8\xff\xe0" + b"picture" + b"\xff\xd9"


def frame_msg(image=FAKE_JPEG):
    return {"jpeg_base64": base64.b64encode(image).decode()}


class FakeLink:
    """Records what the scent controller publishes."""

    is_stub = False

    def __init__(self):
        self.sent = []

    def publish(self, topic, payload, retain=False):
        self.sent.append((topic, json.loads(payload)))
        return True

    def close(self):
        pass


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

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

    def test_readings_use_the_bme688_when_it_reports(self):
        reading = hardware.read_sensors()
        self.assertEqual(reading["climate_source"], "simulated")
        hardware.scent_machine.on_message(
            "xrpod/iaq/reading", b'{"temp_c": 25.0, "humidity_pct": 52.3, "gas_kohm": 80}')
        reading = hardware.read_sensors()
        self.assertEqual(reading["climate_source"], "bme688")
        self.assertEqual(reading["actual_temp_f"], 77.0)
        self.assertEqual(reading["actual_humidity_pct"], 52.3)
        # A reading without temperature or humidity isn't enough.
        hardware.scent_machine.on_message("xrpod/iaq/reading", b'{"gas_kohm": 80}')
        self.assertEqual(hardware.read_sensors()["climate_source"], "simulated")

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
        self.assertEqual(hardware.fan_node.speed, 0)
        self.assertEqual(hardware.scent_machine.active, "none")


class ScentTests(unittest.TestCase):
    def setUp(self):
        self.link, self.clock = FakeLink(), FakeClock()
        self.c = scent.ScentController(self.link, clock=self.clock)

    def last_cmd(self):
        topic, cmd = self.link.sent[-1]
        self.assertEqual(topic, scent.TOPIC_CMD)
        return cmd

    def test_starts_off(self):
        self.assertEqual(self.link.sent, [(scent.TOPIC_CMD, scent.OFF)])

    def test_commands_match_the_firmware(self):
        self.c.apply("lavender", 60)
        self.assertEqual(self.last_cmd(), {"selected_scent": "lavender", "scent_intensity_pct": 60})
        self.c.apply("pine", 130)
        self.assertEqual(self.last_cmd(), {"selected_scent": "pine", "scent_intensity_pct": 100})

    def test_junk_means_off(self):
        for args in [("pine", 0), ("none", 80), ("", 50), (7, 50), (None, 50)]:
            self.c.apply("lavender", 60)
            self.c.apply(*args)
            self.assertEqual(self.last_cmd(), scent.OFF, args)
            self.assertEqual(self.c.active, "none")

    def test_resends_before_the_node_times_out(self):
        self.c.apply("pine", 50)
        sent = len(self.link.sent)
        self.clock.t += 2
        self.c.apply("pine", 50)
        self.assertEqual(len(self.link.sent), sent)  # no spam every loop
        self.clock.t += scent.CMD_REFRESH_S
        self.c.apply("pine", 50)
        self.assertEqual(len(self.link.sent), sent + 1)
        self.assertLess(scent.CMD_REFRESH_S, 15)  # node's kCommandTimeoutMs

    def test_close_always_sends_off(self):
        self.c.apply("pine", 50)
        self.c.off()
        self.c.close()
        self.assertEqual(self.last_cmd(), scent.OFF)
        self.assertEqual(self.link.sent[-2:], [(scent.TOPIC_CMD, scent.OFF)] * 2)

    def test_reports_what_the_node_says(self):
        self.c.apply("pine", 50)
        self.assertEqual(self.c.reported_scent(), "none")  # nothing heard yet
        state = {"selected_scent": "pine", "scent_intensity_pct": 50,
                 "diffusers": [True, False], "reason": "ok", "uptime_s": 12}
        self.c.on_message(scent.TOPIC_NODE, b"online")
        self.c.on_message(scent.TOPIC_STATE, json.dumps(state).encode())
        self.assertEqual(self.c.reported_scent(), "pine")
        self.assertEqual(self.c.node_state["diffusers"], [True, False])
        self.c.on_message(scent.TOPIC_NODE, b"offline")
        self.assertEqual(self.c.reported_scent(), "none")
        self.c.on_message(scent.TOPIC_NODE, b"online")
        self.clock.t += scent.STATE_FRESH_S + 1  # node went quiet
        self.assertEqual(self.c.reported_scent(), "none")

    def test_ignores_bad_messages(self):
        for payload in [b"not json", b"[]", b'{"selected_scent": 5}',
                        b'{"selected_scent": "pine", "scent_intensity_pct": true}',
                        b'{"selected_scent": "pine", "scent_intensity_pct": 900}', b"\xff"]:
            self.c.on_message(scent.TOPIC_STATE, payload)
            self.c.on_message(scent.TOPIC_READING, payload)
        self.assertIsNone(self.c.node_state)
        self.assertIsNone(self.c.reading)
        self.c.on_message(scent.TOPIC_ERROR, b'{"error": "unknown_scent"}')
        self.assertEqual(self.c.last_error, "unknown_scent")
        self.c.on_message(scent.TOPIC_ERROR, b"junk")
        self.assertEqual(self.c.last_error, "unreadable error message")

    def test_status_includes_iaq_reading(self):
        reading = {"temp_c": 22.5, "humidity_pct": 40.1, "pressure_hpa": 1012.0,
                   "gas_kohm": 80.2, "gas_baseline_kohm": 100.0, "baseline_ready": True,
                   "scent_active": "pine", "scent_detected": True}
        self.c.on_message(scent.TOPIC_READING, json.dumps(reading).encode())
        status = self.c.status()
        self.assertTrue(status["scent_detected"])
        self.assertEqual(status["iaq"]["temp_c"], 22.5)
        self.clock.t += scent.READING_FRESH_S + 1
        self.assertIsNone(self.c.status()["iaq"])
        self.assertFalse(self.c.status()["scent_detected"])

    def test_stub_link_reports_the_command(self):
        c = scent.ScentController(scent.StubLink())
        c.apply("pine", 40)
        self.assertEqual(c.status()["scent_active"], "pine")
        self.assertEqual(c.status()["scent_node"], "stub")


class FanTests(unittest.TestCase):
    def setUp(self):
        self.link, self.clock = FakeLink(), FakeClock()
        self.c = fan.FanController(self.link, clock=self.clock)

    def last_cmd(self):
        topic, cmd = self.link.sent[-1]
        self.assertEqual(topic, fan.TOPIC_CMD)
        return cmd

    def test_starts_off(self):
        self.assertEqual(self.link.sent, [(fan.TOPIC_CMD, {"fan_speed_pct": 0})])

    def test_commands_match_the_firmware(self):
        self.c.set_speed(60)
        self.assertEqual(self.last_cmd(), {"fan_speed_pct": 60})
        self.c.set_speed(130)
        self.assertEqual(self.last_cmd(), {"fan_speed_pct": 100})
        self.c.set_speed(-5)
        self.assertEqual(self.last_cmd(), {"fan_speed_pct": 0})

    def test_resends_before_the_node_times_out(self):
        self.c.set_speed(50)
        sent = len(self.link.sent)
        self.clock.t += 2
        self.c.set_speed(50)
        self.assertEqual(len(self.link.sent), sent)  # no spam every loop
        self.clock.t += fan.CMD_REFRESH_S
        self.c.set_speed(50)
        self.assertEqual(len(self.link.sent), sent + 1)
        self.assertLess(fan.CMD_REFRESH_S, 15)  # node's COMMAND_TIMEOUT_MS

    def test_close_always_sends_off(self):
        self.c.set_speed(0)
        self.c.close()
        self.assertEqual(self.link.sent[-2:], [(fan.TOPIC_CMD, {"fan_speed_pct": 0})] * 2)

    def test_reports_what_the_node_says(self):
        self.c.set_speed(80)
        self.assertEqual(self.c.status()["fan_rpm"], 0)  # nothing heard yet
        state = {"fan_speed_pct": 80, "fan_rpm": 1680, "uptime_s": 12}
        self.c.on_message(fan.TOPIC_NODE, b"online")
        self.c.on_message(fan.TOPIC_STATE, json.dumps(state).encode())
        self.assertEqual(self.c.status(), {"fan_rpm": 1680, "fan_node": "online"})
        self.c.on_message(fan.TOPIC_NODE, b"offline")
        self.assertEqual(self.c.status()["fan_rpm"], 0)
        self.c.on_message(fan.TOPIC_NODE, b"online")
        self.clock.t += fan.STATE_FRESH_S + 1  # node went quiet
        self.assertEqual(self.c.status()["fan_rpm"], 0)

    def test_ignores_bad_messages(self):
        for payload in [b"not json", b"[]", b'{"fan_speed_pct": "50", "fan_rpm": 1}',
                        b'{"fan_speed_pct": true, "fan_rpm": 1}', b'{"fan_speed_pct": 50}',
                        b'{"fan_speed_pct": 50, "fan_rpm": 751470}', b"\xff"]:
            self.c.on_message(fan.TOPIC_STATE, payload)
        self.assertIsNone(self.c.node_state)
        self.c.on_message(fan.TOPIC_ERROR, b'{"error": "bad_json"}')
        self.assertEqual(self.c.last_error, "bad_json")
        self.c.on_message(fan.TOPIC_ERROR, b"junk")
        self.assertEqual(self.c.last_error, "unreadable error message")

    def test_stub_link_reports_fake_rpm(self):
        c = fan.FanController(fan.StubLink())
        c.set_speed(40)
        self.assertEqual(c.status(1200), {"fan_rpm": 1200, "fan_node": "stub"})


class MqttTests(unittest.TestCase):
    def test_packet_round_trip(self):
        for n in (0, 127, 128, 16383, 16384, 2_097_151):
            self.assertEqual(len(mqtt.encode_length(n)), 1 if n < 128 else 2 if n < 16384 else 3)
        buf = bytearray(mqtt.publish_packet("xrpod/scent/cmd", '{"a":1}', retain=True))
        ptype, flags, body = mqtt.parse_packet(buf)
        self.assertEqual((ptype, flags), (mqtt.PUBLISH, 1))
        self.assertEqual(mqtt.parse_publish(flags, body)[:2], ("xrpod/scent/cmd", b'{"a":1}'))
        self.assertEqual(buf, bytearray())

    def test_partial_and_oversized_packets(self):
        whole = mqtt.publish_packet("t", "x" * 300)
        buf = bytearray(whole[:-1])
        self.assertIsNone(mqtt.parse_packet(buf))
        buf += whole[-1:]
        self.assertIsNotNone(mqtt.parse_packet(buf))
        with self.assertRaises(mqtt.ProtocolError):
            mqtt.parse_packet(bytearray(b"\x30" + mqtt.encode_length(mqtt.MAX_PACKET + 1)))
        with self.assertRaises(mqtt.ProtocolError):
            mqtt.parse_packet(bytearray(b"\x30\xff\xff\xff\xff\x01"))

    def test_talks_to_a_broker(self):
        """Connect, subscribe, receive and publish against a tiny fake broker."""
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        server.settimeout(5)
        got = {}

        def broker():
            conn, _ = server.accept()
            conn.settimeout(5)
            buf = bytearray()

            def read():
                while True:
                    pkt = mqtt.parse_packet(buf)
                    if pkt:
                        return pkt
                    buf.extend(conn.recv(4096))

            got["connect"] = read()
            conn.sendall(bytes([0x20, 2, 0, 0]))  # CONNACK ok
            got["subscribe"] = read()
            conn.sendall(bytes([0x90, 3, 0, 1, 0]))  # SUBACK
            conn.sendall(mqtt.publish_packet(scent.TOPIC_NODE, "online"))
            got["publish"] = read()
            conn.close()

        thread = threading.Thread(target=broker)
        thread.start()
        received = []
        client = mqtt.MqttClient("127.0.0.1", server.getsockname()[1], client_id="test",
                                 subscriptions=[scent.TOPIC_NODE],
                                 on_message=lambda t, p: received.append((t, p)))
        client.start()
        for _ in range(100):
            if received:
                break
            threading.Event().wait(0.05)
        self.assertTrue(client.publish(scent.TOPIC_CMD, json.dumps(scent.OFF)))
        thread.join(timeout=5)
        client.close()
        server.close()

        self.assertEqual(received, [(scent.TOPIC_NODE, b"online")])
        self.assertEqual(got["connect"][0], mqtt.CONNECT)
        self.assertIn(b"MQTT", got["connect"][2])
        self.assertEqual(got["subscribe"][:2], (mqtt.SUBSCRIBE, 2))
        self.assertIn(scent.TOPIC_NODE.encode(), got["subscribe"][2])
        topic, payload, _, _ = mqtt.parse_publish(got["publish"][1], got["publish"][2])
        self.assertEqual((topic, json.loads(payload)), (scent.TOPIC_CMD, scent.OFF))


    def test_pings_while_only_sending(self):
        """The Pi resends commands every few seconds, so it is always sending.
        If no node publishes, it hears nothing back unless it pings; without a
        ping it would decide the broker is gone and reconnect over and over."""
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        server.settimeout(5)
        pings = []

        def broker():
            conn, _ = server.accept()
            conn.settimeout(0.2)
            buf = bytearray()
            end = time.monotonic() + 4.5
            while time.monotonic() < end:
                try:
                    data = conn.recv(4096)
                except TimeoutError:
                    continue
                if not data:
                    break
                buf += data
                while (pkt := mqtt.parse_packet(buf)) is not None:
                    if pkt[0] == mqtt.CONNECT:
                        conn.sendall(bytes([0x20, 2, 0, 0]))  # CONNACK ok
                    elif pkt[0] == mqtt.PINGREQ:
                        pings.append(time.monotonic())
                        conn.sendall(bytes([0xD0, 0]))  # PINGRESP
            conn.close()

        thread = threading.Thread(target=broker)
        thread.start()
        client = mqtt.MqttClient("127.0.0.1", server.getsockname()[1], client_id="test", keepalive=2)
        client.start()
        end = time.monotonic() + 4
        while time.monotonic() < end:  # keep sending, like the scent/fan resends
            client.publish(scent.TOPIC_CMD, json.dumps(scent.OFF))
            threading.Event().wait(0.3)
        still_connected = client.connected
        client.close()
        thread.join(timeout=5)
        server.close()

        self.assertTrue(pings, "client never pinged while it was only sending")
        self.assertTrue(still_connected, "client dropped a broker that was answering pings")


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
        self.assertEqual(s["control_mode"], "manual")
        self.assertEqual(s["selected_environment"], "none")

    def test_mode_and_environment(self):
        s, rows = self.store.update_settings({"control_mode": "auto", "selected_environment": "beach"})
        self.assertEqual((s["control_mode"], s["selected_environment"]), ("auto", "beach"))
        self.assertEqual({r["field_name"] for r in rows}, {"control_mode", "selected_environment"})
        for patch in [{"control_mode": "AUTO"}, {"control_mode": True},
                      {"selected_environment": "moon"}, {"selected_environment": None}]:
            with self.assertRaises(ValidationError, msg=patch):
                self.store.update_settings(patch)

    def test_auto_mode_blocks_researcher_hardware_changes(self):
        self.store.update_settings({"control_mode": "auto"})
        for patch in [{"fan_speed_pct": 50}, {"heater_on": True}, {"selected_scent": "pine"},
                      {"control_mode": "auto", "target_temp_f": 80}]:
            with self.assertRaises(ValidationError, msg=patch):
                self.store.update_settings(patch)
        self.assertEqual(self.store.get_settings()["fan_speed_pct"], 0)
        # Resending a value that doesn't change anything is fine.
        self.store.update_settings({"fan_speed_pct": 0})
        # The environment can still change in auto.
        s, _ = self.store.update_settings({"selected_environment": "forest"})
        self.assertEqual(s["selected_environment"], "forest")

    def test_researcher_can_take_back_control(self):
        self.store.update_settings({"control_mode": "auto"})
        s, _ = self.store.update_settings({"control_mode": "manual", "fan_speed_pct": 40})
        self.assertEqual((s["control_mode"], s["fan_speed_pct"]), ("manual", 40))

    def test_auto_control_only_acts_in_auto(self):
        with self.assertRaises(ValidationError):
            self.store.update_settings({"fan_speed_pct": 60}, by_auto=True)
        self.store.update_settings({"control_mode": "auto"})
        s, _ = self.store.update_settings({"fan_speed_pct": 60}, by_auto=True)
        self.assertEqual(s["fan_speed_pct"], 60)
        with self.assertRaises(ValidationError):
            self.store.update_settings({"control_mode": "manual"}, by_auto=True)

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
        self.store.update_settings({"selected_scent": "citrus"})
        self.store.close()
        self.store = Store(os.path.join(self.tmp.name, "t.db"))
        self.assertEqual(self.store.get_settings()["selected_scent"], "citrus")

    def test_only_the_scent_nodes_scents(self):
        for name in ("ocean", "rain"):  # the node has lavender, pine and citrus only
            with self.assertRaises(ValidationError):
                self.store.update_settings({"selected_scent": name})
                
    def test_readings(self):
        self.assertIsNone(self.store.get_latest_reading())
        self.store.add_reading({"actual_temp_f": 70.0})
        latest = self.store.add_reading({"actual_temp_f": 71.0})
        self.assertEqual(self.store.get_latest_reading(), latest)


class DataLogStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "t.db"))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_events_newest_first_and_filtered_by_level(self):
        self.store.add_event("info", "pi", "started")
        self.store.add_event("warning", "scent", "Scent node went offline")
        self.store.add_event("error", "pi", "boom")
        self.assertEqual([e["message"] for e in self.store.get_events()],
                         ["boom", "Scent node went offline", "started"])
        self.assertEqual([e["level"] for e in self.store.get_events(min_level="warning")],
                         ["error", "warning"])
        with self.assertRaises(ValidationError):
            self.store.add_event("panic", "pi", "x")
        with self.assertRaises(ValidationError):
            self.store.get_events(min_level="loud")

    def test_event_text_is_capped(self):
        e = self.store.add_event("info", "x" * 100, "m" * 1000)
        self.assertEqual(len(e["source"]), 32)
        self.assertEqual(len(e["message"]), store_module.MAX_EVENT_TEXT)

    def test_session_start_stop_and_one_at_a_time(self):
        s = self.store.start_session("Trial 1")
        self.assertTrue(s["recording"])
        self.assertEqual(s["name"], "Trial 1")
        with self.assertRaises(ValidationError):
            self.store.start_session("Trial 2")
        self.store.add_reading({"actual_temp_f": 70.0})
        done = self.store.stop_session()
        self.assertFalse(done["recording"])
        self.assertEqual(done["readings"], 1)
        with self.assertRaises(ValidationError):
            self.store.stop_session()
        self.assertTrue(self.store.start_session()["name"].startswith("Session "))
        with self.assertRaises(ValidationError):
            self.store.start_session(5)

    def test_session_readings_survive_pruning(self):
        self.store.start_session("keep")
        self.store.add_reading({"actual_temp_f": 70.0})
        self.store.stop_session()
        # Pretend everything is two days old, then prune.
        with self.store._db:
            self.store._db.execute("UPDATE readings SET created_ts = created_ts - 172800")
            self.store._db.execute("UPDATE sessions SET started_ts = started_ts - 172800,"
                                   " ended_ts = ended_ts - 172800")
            self.store._db.execute("INSERT INTO readings (created_ts, created_date, data)"
                                   " VALUES (1, '1970-01-01T00:00:01Z', '{}')")
            self.store._prune_readings(store_module.time.time() - 3600)
        count = self.store._db.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
        self.assertEqual(count, 1)  # the session's reading stayed, the old loose one went

    def test_delete_session(self):
        s = self.store.start_session("gone")
        with self.assertRaises(ValidationError):
            self.store.delete_session(s["id"])  # still recording
        self.store.stop_session()
        self.assertEqual(self.store.delete_session(s["id"]), "gone")
        self.assertEqual(self.store.get_sessions(), [])
        with self.assertRaises(ValidationError):
            self.store.delete_session("abc")

    def test_events_between_includes_settings_changes(self):
        start = store_module.time.time() - 1
        self.store.add_event("warning", "fan", "Fan node went offline")
        self.store.update_settings({"fan_speed_pct": 40}, changed_by="10.42.0.5")
        rows = self.store.events_between(start, store_module.time.time() + 1)
        self.assertEqual([r["source"] for r in rows], ["fan", "settings"])
        self.assertEqual(rows[1]["message"], "fan_speed_pct: 0 -> 40 (by 10.42.0.5)")


class DataLogTests(unittest.TestCase):
    def reading(self, **over):
        base = {"scent_node": "online", "fan_node": "online", "iaq": {"temp_c": 22},
                "heater_running": False, "ac_running": False, "scent_active": "none"}
        return {**base, **over}

    def test_first_reading_only_reports_problems(self):
        w = datalog.EventWatcher()
        self.assertEqual(w.check(self.reading()), [])
        w = datalog.EventWatcher()
        self.assertEqual(w.check(self.reading(fan_node="offline")),
                         [("warning", "fan", "Fan node is offline")])

    def test_changes_become_events(self):
        w = datalog.EventWatcher()
        w.check(self.reading(), {"connected": True, "environment": "beach"})
        events = w.check(self.reading(scent_node="offline", iaq=None, heater_running=True,
                                      scent_active="pine"), {"connected": False},
                         node_errors=[("fan", "bad_json")])
        texts = [e[2] for e in events]
        self.assertIn("Scent node went offline (its outputs turn off)", texts)
        self.assertIn("Fan node reported: bad_json", texts)
        self.assertIn("BME688 sensor stopped reporting (temperature and humidity are simulated)", texts)
        self.assertIn("Headset disconnected", texts)
        self.assertIn("Heater on", texts)
        self.assertIn("Scent now pine", texts)
        # Nothing changed: nothing new.
        self.assertEqual(w.check(self.reading(scent_node="offline", iaq=None, heater_running=True,
                                              scent_active="pine"), {"connected": False}), [])

    def test_stub_nodes_are_quiet(self):
        w = datalog.EventWatcher()
        w.check(self.reading(scent_node="stub", fan_node="stub"))
        self.assertEqual(w.check(self.reading(scent_node="stub", fan_node="stub")), [])

    def test_readings_csv_columns_and_flattening(self):
        text = datalog.readings_csv([
            {"created_date": "2026-11-24T10:00:00Z", "control_mode": "manual",
             "actual_temp_f": 70.5, "heater_running": False, "iaq": {"gas_kohm": 80}, "id": "1"},
            {"created_date": "2026-11-24T10:00:01Z", "control_mode": "auto", "iaq": None, "new_field": 3},
        ])
        lines = text.strip().split("\n")
        header = lines[0].split(",")
        self.assertEqual(header[:3], ["created_date", "control_mode", "selected_environment"])
        self.assertIn("iaq_gas_kohm", header)
        self.assertIn("new_field", header)
        self.assertNotIn("id", header)
        first = dict(zip(header, lines[1].split(",")))
        self.assertEqual(first["actual_temp_f"], "70.5")
        self.assertEqual(first["heater_running"], "false")
        self.assertEqual(first["iaq_gas_kohm"], "80")

    def test_csv_defuses_spreadsheet_formulas(self):
        text = datalog.events_csv([{"created_date": "d", "level": "info", "source": "log",
                                    "message": "=HYPERLINK(\"x\")"}])
        self.assertIn("'=HYPERLINK", text)

    def test_file_name_is_safe(self):
        self.assertEqual(datalog.file_name('session-3-Trial "A"/../x', "readings"),
                         "xrpod-session-3-trial-a-x-readings.csv")


class VrStateTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.vr = VrState(clock=lambda: self.now)

    def test_accepts_good_message(self):
        self.assertIsNone(self.vr.latest())
        state, changed = self.vr.update(GOOD_VR)
        self.assertTrue(changed)
        self.assertEqual(state["zone_type"], "windy")
        self.assertTrue(state["connected"])

    def test_rejects_bad_fields(self):
        bad = [
            {**GOOD_VR, "zone_type": "lava"},
            {**GOOD_VR, "environment": "moon"},
            {**GOOD_VR, "environment": "none"},  # waiting room has no zones
            {**GOOD_VR, "reason": "teleported"},
            {**GOOD_VR, "seq": 0},
            {**GOOD_VR, "seq": True},
            {**GOOD_VR, "seq": 2.5},
            {**GOOD_VR, "session_id": ""},
            {**GOOD_VR, "session_id": "x" * 65},
            {**GOOD_VR, "zone_id": ""},
            {**GOOD_VR, "zone_tracking": "yes"},
            {**GOOD_VR, "fan_speed_pct": 100},  # headset must never drive hardware
            {k: v for k, v in GOOD_VR.items() if k != "reason"},
            {**GOOD_VR, "zone_id": None},  # null zone must be neutral
            {**GOOD_VR, "zone_tracking": False},  # no tracking means no zone
            [], "forest",
        ]
        for msg in bad:
            with self.assertRaises(ValidationError, msg=msg):
                self.vr.update(msg)
        self.assertIsNone(self.vr.latest())

    def test_accepts_waiting_room(self):
        # No world picked in the HUD: the headset is in its waiting room.
        waiting = {**GOOD_VR, "environment": "none", "zone_id": None,
                   "zone_type": "neutral", "zone_tracking": False,
                   "reason": "environment_changed"}
        state, changed = self.vr.update(waiting)
        self.assertTrue(changed)
        self.assertEqual(state["environment"], "none")
        self.assertTrue(state["connected"])

    def test_late_message_is_ignored_but_new_session_wins(self):
        self.vr.update(GOOD_VR)
        late = {**GOOD_VR, "seq": 1, "zone_id": None, "zone_type": "neutral"}
        state, changed = self.vr.update(late)
        self.assertFalse(changed)
        self.assertEqual(state["seq"], 2)
        state, changed = self.vr.update({**late, "session_id": "restarted"})
        self.assertTrue(changed)
        self.assertEqual(state["session_id"], "restarted")

    def test_goes_stale(self):
        self.vr.update(GOOD_VR)
        self.now += STALE_SECONDS + 1
        self.assertFalse(self.vr.latest()["connected"])

    def test_repeat_keeps_it_connected(self):
        # The headset resends its latest message (same seq) every ~5 s while
        # nothing changes. That must count as hearing from it.
        self.vr.update(GOOD_VR)
        for _ in range(3):
            self.now += STALE_SECONDS - 1
            state, changed = self.vr.update(GOOD_VR)
            self.assertFalse(changed)
            self.assertTrue(state["connected"])
            self.assertEqual(state["age_s"], 0)

    def test_late_message_does_not_keep_it_connected(self):
        self.vr.update(GOOD_VR)
        self.now += STALE_SECONDS + 1
        late = {**GOOD_VR, "seq": 1, "zone_id": None, "zone_type": "neutral"}
        state, _ = self.vr.update(late)
        self.assertFalse(state["connected"])
        self.assertEqual(state["seq"], 2)


class VrFrameTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.frame = VrFrame(clock=self.clock)

    def test_keeps_newest_picture_until_stale(self):
        self.assertIsNone(self.frame.latest())
        self.frame.update(frame_msg())
        self.assertEqual(self.frame.latest(), FAKE_JPEG)
        self.clock.t += FRAME_STALE_SECONDS + 0.1
        self.assertIsNone(self.frame.latest())

    def test_rejects_anything_but_a_small_jpeg(self):
        png = b"\x89PNG\r\n\x1a\n" + b"x" * 10
        too_big = b"\xff\xd8\xff" + b"x" * MAX_FRAME_BYTES + b"\xff\xd9"
        for bad in [None, [], {}, {"jpeg_base64": ""}, {"jpeg_base64": 5},
                    {"jpeg_base64": "not base64!"}, {**frame_msg(), "extra": 1},
                    frame_msg(png), frame_msg(too_big)]:
            with self.assertRaises(ValidationError, msg=repr(bad)[:60]):
                self.frame.update(bad)
        self.assertIsNone(self.frame.latest())


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

    def put_vr(self, msg, **headers):
        body = msg if isinstance(msg, str) else json.dumps(msg)
        return self.request("PUT", "/api/vr/state", body,
                            {"Content-Type": "application/json", **headers})

    def test_vr_state_endpoint(self):
        status, body = self.put_vr({**GOOD_VR, "session_id": "web1"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["zone_id"], "clearing-wind")
        self.assertEqual(self.put_vr({**GOOD_VR, "zone_type": "lava"})[0], 400)
        self.assertEqual(self.put_vr("not json")[0], 400)
        # A late message still gets 200 but doesn't replace the newer one.
        late = {**GOOD_VR, "session_id": "web1", "seq": 1, "zone_id": None, "zone_type": "neutral"}
        self.assertEqual(self.put_vr(late)[0], 200)
        status, body = self.request("GET", "/api/vr/state")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["seq"], 2)

    def test_vr_state_keeps_web_protections(self):
        self.assertEqual(self.put_vr(GOOD_VR, Origin="http://evil.example")[0], 403)
        status, _ = self.request("PUT", "/api/vr/state", "x=1",
                                 {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(status, 415)
        self.assertEqual(self.put_vr({**GOOD_VR, "pad": "x" * 10000})[0], 400)
        self.assertEqual(self.request("PUT", "/api/settings", "{}",
                                      {"Content-Type": "application/json"})[0], 405)

    def put_frame(self, msg, **headers):
        return self.request("PUT", "/api/vr/frame", json.dumps(msg),
                            {"Content-Type": "application/json", **headers})

    def test_live_view_frame_round_trip(self):
        self.assertEqual(self.put_frame(frame_msg())[0], 200)
        req = urllib.request.Request(self.base + "/api/vr/frame")  # noqa: S310
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers["Content-Type"], "image/jpeg")
            self.assertEqual(resp.read(), FAKE_JPEG)

    def test_live_view_frame_keeps_web_protections(self):
        self.assertEqual(self.put_frame(frame_msg(), Origin="http://evil.example")[0], 403)
        status, _ = self.request("PUT", "/api/vr/frame", FAKE_JPEG, {"Content-Type": "image/jpeg"})
        self.assertEqual(status, 415)
        self.assertEqual(self.put_frame({"jpeg_base64": "x" * 300_000})[0], 400)
        self.assertEqual(self.put_frame({"jpeg_base64": "aGVsbG8="})[0], 400)  # not a JPEG

    def test_no_live_view_is_204(self):
        server = start_server(self.store, EventHub(), "127.0.0.1", 0, self.tmp.name)
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urllib.request.urlopen(base + "/api/vr/frame", timeout=5) as resp:  # noqa: S310
                self.assertEqual(resp.status, 204)
        finally:
            server.shutdown()

    def put_session(self, msg, **headers):
        return self.request("PUT", "/api/log/session", json.dumps(msg),
                            {"Content-Type": "application/json", **headers})

    def test_data_log_session_and_csv(self):
        self.put_session({"action": "stop"})  # in case another test left one running
        status, body = self.put_session({"action": "start", "name": "Web trial"})
        self.assertEqual(status, 200)
        session = json.loads(body)["session"]
        self.assertTrue(session["recording"])
        self.assertEqual(self.put_session({"action": "start"})[0], 400)  # one at a time
        self.store.add_reading({"actual_temp_f": 70.0, "control_mode": "manual"})
        self.assertEqual(self.put_session({"action": "stop"})[0], 200)

        req = urllib.request.Request(f"{self.base}/api/log/readings.csv?session={session['id']}")  # noqa: S310
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
            self.assertTrue(resp.headers["Content-Type"].startswith("text/csv"))
            self.assertIn("attachment", resp.headers["Content-Disposition"])
            text = resp.read().decode()
        self.assertTrue(text.startswith("created_date,control_mode"))
        self.assertIn("70.0", text)

        status, text = self.request("GET", "/api/log/events.csv?minutes=5")
        self.assertEqual(status, 200)
        self.assertIn("Recording started: Web trial", text)
        status, body = self.request("GET", "/api/log/events?level=info&limit=5")
        self.assertEqual(status, 200)
        self.assertTrue(any("Recording stopped" in e["message"] for e in json.loads(body)))
        status, body = self.request("GET", "/api/log/sessions")
        self.assertIn("Web trial", body)

    def test_data_log_rejects_bad_requests(self):
        self.assertEqual(self.put_session({"action": "explode"})[0], 400)
        self.assertEqual(self.put_session({"action": "start", "extra": 1})[0], 400)
        self.assertEqual(self.put_session({"action": "start"}, Origin="http://evil.example")[0], 403)
        self.assertEqual(self.request("GET", "/api/log/readings.csv?minutes=0")[0], 400)
        self.assertEqual(self.request("GET", "/api/log/readings.csv?minutes=abc")[0], 400)
        self.assertEqual(self.request("GET", "/api/log/readings.csv?session=999")[0], 400)
        self.assertEqual(self.request("GET", "/api/log/events?level=loud")[0], 400)
        self.assertEqual(self.request("GET", "/api/log/nope")[0], 404)

    def test_read_endpoints(self):
        self.assertEqual(self.request("GET", "/api/settings")[0], 200)
        self.assertEqual(self.request("GET", "/api/history?limit=5")[0], 200)
        self.assertEqual(self.request("GET", "/api/history?limit=abc")[0], 400)
        self.assertEqual(self.request("GET", "/api/readings/latest")[0], 200)
        self.assertEqual(self.request("GET", "/api/nope")[0], 404)


if __name__ == "__main__":
    unittest.main()