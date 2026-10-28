"""
XRPod hardware: sensors and actuators on the Raspberry Pi.

Heater, AC and fan are STUBS until you fill in the TODO(hardware) parts, so
the whole system runs on a laptop for testing. Scent and the air sensors
live on the ESP32 scent / IAQ node; scent.py talks to it over MQTT once
MQTT_HOST is set.

Safety rules this module enforces no matter what the HUD asks for:
  * the heater and AC never run at the same time,
  * percentages are clamped to 0-100 and junk values mean "off",
  * cleanup() turns every output off.
"""

import logging
import random

from scent import ScentHub

log = logging.getLogger("xrpod.hardware")

# Last state we drove the hardware to; read_sensors() reports it back.
state = {
    "ac_running": False,
    "heater_running": False,
    "fan_pct": 0,
}
scent_hub = None  # ScentHub, created in setup()


def setup():
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
    global scent_hub
    log.info("hardware: using STUBS for heater/AC/fan")
    scent_hub = ScentHub()


def cleanup():
    """Put every output in a safe state on exit.

    TODO(hardware): also stop PWM and call GPIO.cleanup().
    """
    set_heater_relay(False)
    set_ac_relay(False)
    set_fan_pwm(0)
    if scent_hub:
        scent_hub.close()
    log.info("hardware: all outputs off")


# --------------------------------------------------------------------------
# Sensors (temperature, humidity and air quality come from the scent node)
# --------------------------------------------------------------------------
def _rounded(value, digits):
    return round(value, digits) if isinstance(value, float) else None


def read_sensors():
    """Return one reading (same fields the HUD's live readouts show).

    Temperature, humidity and IAQ come from the scent node's IAQ sensor.
    Without a node (stub link, laptop testing) temperature and humidity are
    fake; with a real node that has gone quiet they're None.

    TODO(hardware): fan_rpm = read_tach_rpm(FAN_TACH_PIN)
    """
    env = (scent_hub.environment() if scent_hub else None) or {}
    if env or (scent_hub and not scent_hub.is_stub):
        temp_c, humidity = env.get("t_c"), env.get("rh")
        temp_f = temp_c * 9 / 5 + 32 if temp_c is not None else None
    else:
        temp_f = 70.0 + random.uniform(-1.5, 1.5)  # noqa: S311 - stub data
        humidity = 45.0 + random.uniform(-3, 3)  # noqa: S311
    fake_rpm = state["fan_pct"] * 30 + random.uniform(-20, 20) if state["fan_pct"] else 0  # noqa: S311

    return {
        "actual_temp_f": _rounded(temp_f, 1),
        "actual_humidity_pct": _rounded(humidity, 1),
        "pressure_hpa": _rounded(env.get("p_hpa"), 1),
        "iaq": _rounded(env.get("iaq"), 0),
        "iaq_accuracy": env.get("iaq_acc"),
        "eco2_ppm": _rounded(env.get("eco2_ppm"), 0),
        "bvoc_ppm": _rounded(env.get("bvoc_ppm"), 2),
        "ac_running": state["ac_running"],
        "heater_running": state["heater_running"],
        "fan_rpm": max(0, round(fake_rpm)),
        "scent_active": scent_hub.active if scent_hub else "none",
        "scent_check": scent_hub.check() if scent_hub else None,
    }


# --------------------------------------------------------------------------
# Actuators (STUB)
# --------------------------------------------------------------------------
def set_heater_relay(on):
    # TODO(hardware): GPIO.output(HEATER_RELAY_PIN, GPIO.HIGH if on else GPIO.LOW)
    state["heater_running"] = on


def set_ac_relay(on):
    # TODO(hardware): GPIO.output(AC_RELAY_PIN, GPIO.HIGH if on else GPIO.LOW)
    state["ac_running"] = on


def set_fan_pwm(pct):
    # TODO(hardware): fan_pwm.ChangeDutyCycle(pct)
    state["fan_pct"] = pct


def to_pct(value):
    """Coerce a value into an int 0-100. Anything that isn't a finite number
    (None, "abc", NaN, True) becomes 0, i.e. off."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    if value != value or value in (float("inf"), float("-inf")):  # NaN / inf
        return 0
    return max(0, min(100, int(value)))


def apply_settings(settings):
    """Drive the hardware to match the desired settings."""
    heater_on = settings.get("heater_on") is True
    ac_on = settings.get("ac_on") is True
    if heater_on and ac_on:
        # The server keeps these exclusive, but never run both on real hardware.
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

    set_fan_pwm(to_pct(settings.get("fan_speed_pct")))

    scent = settings.get("selected_scent")
    scent_hub.apply(
        scent if isinstance(scent, str) else "none",
        to_pct(settings.get("scent_intensity_pct")),
    )

    # TODO(control): target_temp_f / target_humidity_pct are setpoints. If the
    # Pi should run a thermostat loop (rather than the HUD toggling relays
    # manually), compare them against read_sensors() here.
