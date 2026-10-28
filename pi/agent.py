#!/usr/bin/env python3
"""
XRPod pod controller. Runs on the Raspberry Pi 5 and does everything:

  * serves the HUD website and its API on the local network (web.py),
  * stores settings, readings and change history in SQLite (store.py),
  * every CONTROL_SECONDS reads the sensors and drives the heater, AC, fan
    and scent node to match the settings (hardware.py, scent.py).

Run it:
    cd hud && npm run build    # once: builds the HUD into hud/dist/
    python3 pi/agent.py        # from the repo root; open http://<pi-address>:8080

It also runs on a laptop with stubbed hardware, which is the easiest way to
test the HUD.

Settings (environment variables):
  HUD_HOST          address to listen on (default 0.0.0.0 = whole network)
  HUD_PORT          port (default 8080)
  XRPOD_DB          database file (default xrpod.db next to this script)
  XRPOD_STATIC_DIR  built HUD (default ../hud/dist)
  CONTROL_SECONDS   sensor/control loop interval (default 2)
  MQTT_HOST         Mosquitto broker for the scent / IAQ node, e.g. 127.0.0.1
                    (unset = stub, no node)
  MQTT_PORT         default 1883
  MQTT_USER, MQTT_PASS  broker login (keep them in /etc/xrpod.env, not here)
  LOG_LEVEL         e.g. DEBUG

Uses the Python standard library, plus python3-paho-mqtt (apt) for the scent
node and RPi.GPIO (ships with Raspberry Pi OS) once you drive real pins.
"""

import logging
import os
import signal
import threading
import time
from pathlib import Path

import hardware
from store import Store
from web import EventHub, start_server

HERE = Path(__file__).resolve().parent
HUD_HOST = os.environ.get("HUD_HOST", "0.0.0.0")  # noqa: S104 - LAN server by design
HUD_PORT = int(os.environ.get("HUD_PORT", "8080"))
DB_PATH = os.environ.get("XRPOD_DB", str(HERE / "xrpod.db"))
STATIC_DIR = os.environ.get("XRPOD_STATIC_DIR", str(HERE.parent / "hud" / "dist"))
CONTROL_SECONDS = float(os.environ.get("CONTROL_SECONDS", "2"))

log = logging.getLogger("xrpod")


def control_loop(store, hub, wake, stop):
    """Read sensors, publish the reading, and apply the latest settings.
    `wake` is set when settings change so the hardware reacts immediately."""
    while not stop.is_set():
        try:
            hardware.apply_settings(store.get_settings())
            reading = store.add_reading(hardware.read_sensors())
            hub.publish("reading", reading)
        except Exception:
            # Keep controlling; a bad sensor read must not stop the loop.
            log.exception("control loop error")
        wake.wait(CONTROL_SECONDS)
        wake.clear()


def main():
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    stop = threading.Event()
    wake = threading.Event()
    # systemd stops services with SIGTERM; treat it like Ctrl+C.
    signal.signal(signal.SIGTERM, lambda *_: stop.set())

    store = Store(DB_PATH)
    hub = EventHub()
    hardware.setup()
    server = start_server(store, hub, HUD_HOST, HUD_PORT, STATIC_DIR, on_settings_changed=wake.set)
    loop = threading.Thread(target=control_loop, args=(store, hub, wake, stop), name="control")
    loop.start()

    try:
        while not stop.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        log.info("stopping")
        stop.set()
        wake.set()
        loop.join(timeout=5)
        server.shutdown()
        hardware.cleanup()
        store.close()


if __name__ == "__main__":
    main()
