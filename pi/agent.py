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
  CONTROL_SECONDS   sensor/control loop interval, and how often a reading is
                    saved (default 1: the data log's 1 Hz)
  SCENT_HARDWARE    set to "mqtt" to talk to the ESP32 scent node
  FAN_HARDWARE      set to "mqtt" to talk to the ESP32 fan node
  MQTT_HOST         MQTT broker (default 127.0.0.1, Mosquitto on this Pi)
  MQTT_PORT         broker port (default 1883)
  MQTT_USER, MQTT_PASSWORD   broker login, if it needs one  LOG_LEVEL         e.g. DEBUG

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
from datalog import EventWatcher
from simulation_executor import SimulationExecutor
from store import Store
from vr import VrState
from web import EventHub, start_server

HERE = Path(__file__).resolve().parent
HUD_HOST = os.environ.get("HUD_HOST", "0.0.0.0")  # noqa: S104 - LAN server by design
HUD_PORT = int(os.environ.get("HUD_PORT", "8080"))
DB_PATH = os.environ.get("XRPOD_DB", str(HERE / "xrpod.db"))
STATIC_DIR = os.environ.get("XRPOD_STATIC_DIR", str(HERE.parent / "hud" / "dist"))
CONTROL_SECONDS = float(os.environ.get("CONTROL_SECONDS", "1"))
# The same control-loop error is logged as an event at most this often.
REPEAT_ERROR_SECONDS = 60

log = logging.getLogger("xrpod")


class UnavailableModel:
    """Stands in for the ML model when it can't load (e.g. pandas/joblib/
    scikit-learn not installed), so the rest of the pod keeps running."""

    def predict(self, reading):
        return {"prediction": "UNKNOWN", "confidence": 0.0}


def load_ml_model():
    try:
        from ml_inference import PhysicalEnvironmentModel  # needs pandas, joblib, scikit-learn
        return PhysicalEnvironmentModel()
    except Exception:
        log.exception("ML model unavailable; AI status will show UNKNOWN")
        return UnavailableModel()


def run_ai(store, hub, vr, reading, settings, ai_controller, ml_model, arbiter, simulation_executor):
    """Salma's AI supervisor: predict, recommend, arbitrate, and run the
    decision in SIMULATION only (it never drives the real hardware yet).
    Publishes the result to the HUD's AI status card."""
    try:
        physical_prediction = ml_model.predict(reading)
    except Exception:
        log.exception("ML inference failed")
        physical_prediction = {"prediction": "UNKNOWN", "confidence": 0.0}

    recommendation = ai_controller.recommend(settings=settings, reading=reading, vr_state=vr.latest())
    decision = arbiter.resolve(settings=settings, recommendation=recommendation, reading=reading)

    current_settings = store.get_settings()
    if current_settings.get("control_mode") != settings.get("control_mode"):
        simulation_result = simulation_executor.stop("Operating mode changed")
    else:
        simulation_result = simulation_executor.execute(
            decision=decision, current_settings=current_settings, generation=arbiter.generation
        )

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


def log_event(store, hub, level, source, message):
    """Save an event and show it in the HUD straight away."""
    try:
        hub.publish("event", store.add_event(level, source, message))
    except Exception:
        log.exception("couldn't save event: %s", message)


def build_reading(settings, vr):
    """One reading for the data log: the sensors and actuator states, plus
    the operating mode, the world picked and what the headset reports."""
    state = vr.latest() or {}
    connected = bool(state.get("connected"))
    return {
        **hardware.read_sensors(),
        "control_mode": settings.get("control_mode"),
        "selected_environment": settings.get("selected_environment"),
        "vr_connected": connected,
        "vr_environment": state.get("environment") if connected else None,
        "vr_zone": state.get("zone_id") if connected else None,
    }


def control_loop(store, hub, wake, stop, vr, ai_controller=None, ml_model=None,
                 arbiter=None, simulation_executor=None):
    """Read sensors, save and publish the reading, log what changed, and
    apply the latest settings. `wake` is set when settings change so the
    hardware reacts immediately."""
    watcher = EventWatcher()
    ai_on = ai_controller is not None and arbiter is not None
    if ai_on:
        ml_model = ml_model or UnavailableModel()
        simulation_executor = simulation_executor or SimulationExecutor()
    last_error, last_error_at = None, 0.0
    while not stop.is_set():
        try:
            settings = store.get_settings()
            hardware.apply_settings(settings)
            raw = build_reading(settings, vr)
            for level, source, message in watcher.check(raw, vr.latest(), hardware.take_node_errors()):
                log_event(store, hub, level, source, message)
            hub.publish("reading", store.add_reading(raw))
            if ai_on:
                run_ai(store, hub, vr, raw, settings, ai_controller, ml_model, arbiter, simulation_executor)
        except Exception as err:
            # Keep controlling; a bad sensor read must not stop the loop.
            log.exception("control loop error")
            if ai_on:
                simulation_executor.stop("Control loop failure")
            text = f"Control loop error: {type(err).__name__}: {err}"
            if text != last_error or time.monotonic() - last_error_at > REPEAT_ERROR_SECONDS:
                last_error, last_error_at = text, time.monotonic()
                log_event(store, hub, "error", "pi", text)
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
    server = start_server(store, hub, HUD_HOST, HUD_PORT, STATIC_DIR, on_settings_changed=wake.set, vr=vr)
    log_event(store, hub, "info", "pi", "Pi software started")
    loop = threading.Thread(
        target=control_loop,
        args=(store, hub, wake, stop, vr, AIController(), load_ml_model(), ControlArbiter(), SimulationExecutor()),
        name="control",
    )
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
        log_event(store, hub, "info", "pi", "Pi software stopped (all outputs off)")
        store.close()


if __name__ == "__main__":
    main()
