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
from control_arbiter import ControlArbiter
from ml_inference import PhysicalEnvironmentModel
from simulation_executor import SimulationExecutor
from store import Store
from vr import VrState
from web import EventHub, start_server


HERE = Path(__file__).resolve().parent
HUD_HOST = os.environ.get("HUD_HOST", "0.0.0.0")
HUD_PORT = int(os.environ.get("HUD_PORT", "8080"))
DB_PATH = os.environ.get("XRPOD_DB", str(HERE / "xrpod.db"))
STATIC_DIR = os.environ.get(
    "XRPOD_STATIC_DIR",
    str(HERE.parent / "hud" / "dist"),
)
CONTROL_SECONDS = float(os.environ.get("CONTROL_SECONDS", "2"))

log = logging.getLogger("xrpod")


class UnavailableModel:
    def predict(self, reading):
        return {
            "prediction": "UNKNOWN",
            "confidence": 0.0,
        }


def control_loop(
    store, hub, wake, stop, vr, ai_controller,
    ml_model, arbiter, simulation_executor=None
):
    if simulation_executor is None:
        simulation_executor = SimulationExecutor()

    while not stop.is_set():
        try:
            settings = store.get_settings()
            reading = hardware.read_sensors()
            vr_state = vr.latest()

            try:
                physical_prediction = ml_model.predict(reading)
            except Exception:
                log.exception("ML inference failed")
                physical_prediction = {
                    "prediction": "UNKNOWN",
                    "confidence": 0.0,
                }

            recommendation = ai_controller.recommend(
                settings=settings,
                reading=reading,
                vr_state=vr_state,
            )

            decision = arbiter.resolve(
                settings=settings,
                recommendation=recommendation,
                reading=reading,
            )

            current_settings = store.get_settings()

            if current_settings.get("control_mode") != settings.get("control_mode"):
                simulation_result = simulation_executor.stop(
                    "Operating mode changed"
                )
            else:
                simulation_result = simulation_executor.execute(
                    decision=decision,
                    current_settings=current_settings,
                    generation=arbiter.generation,
                )

            saved_reading = store.add_reading(reading)
            hub.publish("reading", saved_reading)

            hub.publish("ai", {
                "active": recommendation.active,
                "environment": recommendation.environment,
                "zone": recommendation.zone,
                "target_temp_f": recommendation.target_temp_f,
                "fan_speed_pct": recommendation.fan_speed_pct,
                "reason": recommendation.reason,
                "control_mode": current_settings["control_mode"],
                "physical_environment": physical_prediction["prediction"],
                "model_confidence": physical_prediction["confidence"],
                "control_source": decision.source,
                "control_authorized": decision.authorized,
                "control_reason": decision.reason,
                "effective_settings": decision.settings,
                "control_generation": arbiter.generation,
                "execution_mode": "simulation",
                "simulation": simulation_result,
            })

            hardware.apply_settings(store.get_settings())

        except Exception:
            log.exception("XRPOD control loop error")
            simulation_executor.stop("Control loop failure")

        wake.wait(CONTROL_SECONDS)
        wake.clear()


def main():
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    stop = threading.Event()
    wake = threading.Event()

    signal.signal(signal.SIGTERM, lambda *_: stop.set())

    store = Store(DB_PATH)
    hub = EventHub()
    vr = VrState()

    ai_controller = AIController()
    arbiter = ControlArbiter()
    simulation_executor = SimulationExecutor()

    try:
        ml_model = PhysicalEnvironmentModel()
    except Exception:
        log.exception("ML model unavailable")
        ml_model = UnavailableModel()

    server = None
    loop = None

    try:
        hardware.setup()

        server = start_server(
            store,
            hub,
            HUD_HOST,
            HUD_PORT,
            STATIC_DIR,
            on_settings_changed=wake.set,
            vr=vr,
        )

        loop = threading.Thread(
            target=control_loop,
            args=(
                store,
                hub,
                wake,
                stop,
                vr,
                ai_controller,
                ml_model,
                arbiter,
                simulation_executor,
            ),
            name="control",
        )

        loop.start()

        while not stop.is_set():
            time.sleep(0.5)

    except KeyboardInterrupt:
        pass

    finally:
        log.info("stopping")
        stop.set()
        wake.set()

        if loop is not None:
            loop.join(timeout=5)

        if server is not None:
            server.shutdown()
            server.server_close()

        hardware.cleanup()
        store.close()


if __name__ == "__main__":
    main()