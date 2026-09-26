#!/usr/bin/env python3
"""
XRPod Pi agent — runs on the Raspberry Pi, NOT part of the web build.

Every POLL_SECONDS it:
  1. reads the pod's sensors,
  2. POSTs the reading to the push-sensor-reading backend function,
  3. fetches the current PodSettings record (what the HUD wants), and
  4. drives the relays / PWM outputs to match.

WHAT TO FILL IN
---------------
  APP_DOMAIN    Your deployed site's domain, e.g. "xrpod.base44.app"
                (no https://, no trailing slash).
  APP_ID        Your Base44 app id (the "id" in base44/.app.jsonc, or run
                `base44 dashboard open` and copy it from the URL). Needed to
                read PodSettings from the entities API.
  PI_AGENT_KEY  Must match the PI_AGENT_KEY secret set with
                `base44 secrets set PI_AGENT_KEY=...`.
  read_sensors()     Replace the stub with real sensor reads (e.g. a DHT22 /
                     SHT31 for temp+humidity, a tach input for fan RPM).
  apply_settings()   Replace the stubs with real GPIO relay + PWM calls
                     (heater relay, AC relay, fan PWM, scent diffuser).

All three settings can also come from environment variables of the same
name, which is handy for a systemd unit:

    APP_DOMAIN=xrpod.base44.app APP_ID=... PI_AGENT_KEY=... python3 agent.py

Uses only the Python standard library, so no pip install is required until
you add real sensor/GPIO libraries.
"""

import json
import logging
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request

# --------------------------------------------------------------------------
# Configuration — fill these in (or set the matching environment variables)
# --------------------------------------------------------------------------
APP_DOMAIN = os.environ.get("APP_DOMAIN", "YOUR-APP.base44.app")
APP_ID = os.environ.get("APP_ID", "YOUR_APP_ID")
PI_AGENT_KEY = os.environ.get("PI_AGENT_KEY", "CHANGE_ME")

POLL_SECONDS = float(os.environ.get("POLL_SECONDS", "3"))
HTTP_TIMEOUT_SECONDS = 10

BASE_URL = f"https://{APP_DOMAIN}"
PUSH_READING_URL = f"{BASE_URL}/functions/push-sensor-reading"
# If your domain doesn't route /functions/, the SDK's equivalent path is:
#   f"{BASE_URL}/api/apps/{APP_ID}/functions/push-sensor-reading"
# Oldest PodSettings record is the canonical one (the HUD uses the same rule).
POD_SETTINGS_URL = (
    f"{BASE_URL}/api/apps/{APP_ID}/entities/PodSettings?"
    + urllib.parse.urlencode({"sort": "created_date", "limit": 1})
)

# Mirrors DEFAULT_SETTINGS in src/lib/podSettings.js — used until the first
# successful fetch so the hardware starts in a safe, everything-off state.
DEFAULT_SETTINGS = {
    "target_temp_f": 72,
    "target_humidity_pct": 45,
    "fan_speed_pct": 0,
    "ac_on": False,
    "heater_on": False,
    "selected_scent": "none",
    "scent_intensity_pct": 50,
}

log = logging.getLogger("xrpod-agent")

# Last state we drove the hardware to; read_sensors() reports it back.
hardware_state = {
    "ac_running": False,
    "heater_running": False,
    "fan_pct": 0,
    "scent": "none",
}


# --------------------------------------------------------------------------
# Hardware setup
# --------------------------------------------------------------------------
def setup_hardware():
    """One-time GPIO / sensor initialisation.

    TODO(hardware): e.g.
        import RPi.GPIO as GPIO            # or gpiozero / lgpio
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(HEATER_RELAY_PIN, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(AC_RELAY_PIN, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(FAN_PWM_PIN, GPIO.OUT)
        fan_pwm = GPIO.PWM(FAN_PWM_PIN, 25_000); fan_pwm.start(0)
        dht = adafruit_dht.DHT22(board.D4)
    """
    log.info("setup_hardware(): using STUBS — no real GPIO configured")


def cleanup_hardware():
    """Put every output in a safe state on exit.

    TODO(hardware): turn relays off, stop PWM, GPIO.cleanup().
    """
    log.info("cleanup_hardware(): all outputs off (stub)")


# --------------------------------------------------------------------------
# Sensors (STUB)
# --------------------------------------------------------------------------
def read_sensors():
    """Return a dict matching the SensorReading entity.

    TODO(hardware): replace the fake numbers below with real reads, e.g.
        temp_c = dht.temperature; humidity = dht.humidity
        fan_rpm = read_tach_rpm(FAN_TACH_PIN)
    Keep actual_temp_f and actual_humidity_pct — the backend requires them.
    """
    fake_temp_f = 70.0 + random.uniform(-1.5, 1.5)
    fake_humidity = 45.0 + random.uniform(-3, 3)
    fake_rpm = hardware_state["fan_pct"] * 30 + random.uniform(-20, 20)

    return {
        "actual_temp_f": round(fake_temp_f, 1),
        "actual_humidity_pct": round(fake_humidity, 1),
        "ac_running": hardware_state["ac_running"],
        "heater_running": hardware_state["heater_running"],
        "fan_rpm": max(0, round(fake_rpm)),
        "scent_active": hardware_state["scent"],
        "reading_source": "pi-agent",
    }


# --------------------------------------------------------------------------
# Actuators (STUB)
# --------------------------------------------------------------------------
def set_heater_relay(on):
    # TODO(hardware): GPIO.output(HEATER_RELAY_PIN, GPIO.HIGH if on else GPIO.LOW)
    hardware_state["heater_running"] = on


def set_ac_relay(on):
    # TODO(hardware): GPIO.output(AC_RELAY_PIN, GPIO.HIGH if on else GPIO.LOW)
    hardware_state["ac_running"] = on


def set_fan_pwm(pct):
    # TODO(hardware): fan_pwm.ChangeDutyCycle(pct)
    hardware_state["fan_pct"] = pct


def set_scent(scent, intensity_pct):
    # TODO(hardware): select the cartridge for `scent` and set the diffuser
    # PWM to intensity_pct; "none" means diffuser off.
    hardware_state["scent"] = scent


def apply_settings(settings):
    """Drive the hardware to match the desired PodSettings."""
    heater_on = bool(settings.get("heater_on"))
    ac_on = bool(settings.get("ac_on"))
    if heater_on and ac_on:
        # The HUD keeps these exclusive, but never run both on real hardware.
        log.warning("heater_on and ac_on both set — turning both off")
        heater_on = ac_on = False

    # Always switch the one going off before the one coming on.
    if not heater_on:
        set_heater_relay(False)
    if not ac_on:
        set_ac_relay(False)
    if heater_on:
        set_heater_relay(True)
    if ac_on:
        set_ac_relay(True)

    fan_pct = clamp(int(settings.get("fan_speed_pct") or 0), 0, 100)
    set_fan_pwm(fan_pct)

    scent = settings.get("selected_scent") or "none"
    intensity = clamp(int(settings.get("scent_intensity_pct") or 0), 0, 100)
    set_scent(scent, intensity if scent != "none" else 0)

    # TODO(control): target_temp_f / target_humidity_pct are setpoints. If the
    # Pi should run a thermostat loop (rather than the HUD toggling relays
    # manually), compare them against read_sensors() here.


def clamp(value, lo, hi):
    return max(lo, min(hi, value))


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
def http_json(method, url, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    req.add_header("X-App-Id", APP_ID)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


def push_reading(reading):
    return http_json(
        "POST", PUSH_READING_URL, reading, headers={"x-agent-key": PI_AGENT_KEY}
    )


def fetch_settings():
    records = http_json("GET", POD_SETTINGS_URL)
    if isinstance(records, list) and records:
        return records[0]
    return None


def describe_http_error(err):
    if isinstance(err, urllib.error.HTTPError):
        detail = err.read().decode(errors="replace")[:200]
        return f"HTTP {err.code}: {detail}"
    return str(err)


# --------------------------------------------------------------------------
# Main loop
# --------------------------------------------------------------------------
def main():
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if "YOUR" in APP_DOMAIN or "YOUR" in APP_ID or PI_AGENT_KEY == "CHANGE_ME":
        log.warning("APP_DOMAIN / APP_ID / PI_AGENT_KEY are still placeholders")

    setup_hardware()
    apply_settings(DEFAULT_SETTINGS)
    last_settings = None

    try:
        while True:
            started = time.monotonic()

            try:
                reading = read_sensors()
                push_reading(reading)
                log.debug("pushed reading %s", reading)
            except Exception as err:  # keep looping on any failure
                log.error("push reading failed: %s", describe_http_error(err))

            try:
                settings = fetch_settings()
                if settings is None:
                    log.warning("no PodSettings record yet — open the HUD once to create it")
                else:
                    apply_settings(settings)
                    if settings != last_settings:
                        log.info(
                            "applied settings: temp=%s°F hum=%s%% fan=%s%% heater=%s ac=%s scent=%s@%s%%",
                            settings.get("target_temp_f"),
                            settings.get("target_humidity_pct"),
                            settings.get("fan_speed_pct"),
                            settings.get("heater_on"),
                            settings.get("ac_on"),
                            settings.get("selected_scent"),
                            settings.get("scent_intensity_pct"),
                        )
                        last_settings = settings
            except Exception as err:
                # Keep the last applied state; don't flap hardware on a blip.
                log.error("fetch settings failed: %s", describe_http_error(err))

            time.sleep(max(0.0, POLL_SECONDS - (time.monotonic() - started)))
    except KeyboardInterrupt:
        log.info("stopping")
    finally:
        cleanup_hardware()


if __name__ == "__main__":
    main()
