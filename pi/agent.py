#!/usr/bin/env python3
"""
XRPod pod controller. Runs on the Raspberry Pi 5 and does everything:

  * serves the HUD website and its API on the local network (web.py),
  * stores settings, readings and change history in SQLite (store.py),
  * every CONTROL_SECONDS reads the sensors and drives the heater, AC, fan
    and scent machine to match the settings (hardware.py, scent.py).

Run it:
    cd hud && npm run build    # once: builds the HUD into hud/dist/
    python3 pi/agent.py        # then open http://<pi-address>:8080

It also runs on a laptop with stubbed hardware, which is the easiest way to
test the HUD.

Settings (environment variables):
  HUD_HOST          address to listen on (default 0.0.0.0 = whole network)
  HUD_PORT          port (default 8080)
  XRPOD_DB          database file (default xrpod.db next to this script)
  XRPOD_STATIC_DIR  built HUD (default ../hud/dist)
  CONTROL_SECONDS   sensor/control loop interval (default 2)
  SCENT_HARDWARE    set to "gpio" to drive the scent machine's real pins
  LOG_LEVEL         e.g. DEBUG

Uses only the Python standard library (plus RPi.GPIO, which Raspberry Pi OS
ships with, once you drive real pins).
"""

import logging
import os
import signal
import threading
import time
from pathlib import Path

import hardware
from ai_controller import AIController
from ml_inference import PhysicalEnvironmentModel
from store import Store
from vr import VrState
from web import EventHub, start_server

HERE = Path(__file__).resolve().parent
HUD_HOST = os.environ.get("HUD_HOST", "0.0.0.0")  # noqa: S104 - LAN server by design
HUD_PORT = int(os.environ.get("HUD_PORT", "8080"))
DB_PATH = os.environ.get("XRPOD_DB", str(HERE / "xrpod.db"))
STATIC_DIR = os.environ.get("XRPOD_STATIC_DIR", str(HERE.parent / "hud" / "dist"))
CONTROL_SECONDS = float(os.environ.get("CONTROL_SECONDS", "2"))

log = logging.getLogger("xrpod")

def control_loop(store, hub, wake, stop, vr, ai_controller, ml_model):
    """
    Read sensors, generate AI recommendations,
    publish live updates, and preserve existing
    hardware behavior.

    AI recommendations are NOT applied to hardware.
    """

    while not stop.is_set():
        try:
            # 1. Get current pod settings
            settings = store.get_settings()

            # 2. Read simulated sensor data
            reading = hardware.read_sensors()
            # Predict physical environmental conditions.
            # This is monitoring-only; it does not control hardware.
            physical_prediction = ml_model.predict(reading)
            

            # 3. Get latest VR environment information
            vr_state = vr.latest()

            # 4. Generate AI recommendation
            recommendation = ai_controller.recommend(
                settings=settings,
                reading=reading,
                vr_state=vr_state
            )

            # 5. Save and publish sensor readings
            saved_reading = store.add_reading(reading)
            hub.publish("reading", saved_reading)

            # 6. Publish AI status for the HUD
            ai_status = {
                "active": recommendation.active,
                "environment": recommendation.environment,
                "zone": recommendation.zone,
                "target_temp_f": recommendation.target_temp_f,
                "fan_speed_pct": recommendation.fan_speed_pct,
                "reason": recommendation.reason,
                "control_mode": settings["control_mode"],
                "physical_environment": physical_prediction["prediction"],
                "model_confidence": physical_prediction["confidence"],
            }

            hub.publish("ai", ai_status)

            # 7. Preserve the existing hardware behavior
            # Recommendations are NOT applied.
            hardware.apply_settings(store.get_settings())

        except Exception:
            log.exception("XRPOD control loop error")

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
    vr = VrState()  # latest headset report; auto mode will read vr.latest()
    hardware.setup()
    # Initialize the XRPOD AI supervisor
    ai_controller = AIController()
    ml_model = PhysicalEnvironmentModel()
    server = start_server(store, hub, HUD_HOST, HUD_PORT, STATIC_DIR, on_settings_changed=wake.set, vr=vr)
    loop = threading.Thread(target=control_loop, args=(store, hub, wake, stop, vr, ai_controller, ml_model), name="control")
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
