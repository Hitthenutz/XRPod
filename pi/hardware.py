"""
XRPod hardware: sensors and actuators on the Raspberry Pi.

Everything here is a STUB until you fill in the TODO(hardware) parts, so the
whole system runs on a laptop for testing. scent.py (the scent machine) is
already wired up; set SCENT_HARDWARE=gpio to drive its real pins.

Safety rules this module enforces no matter what the HUD asks for:
  * the heater and AC never run at the same time,
  * percentages are clamped to 0-100 and junk values mean "off",
  * cleanup() turns every output off.
"""

import logging
import random

from scent import ScentController

log = logging.getLogger("xrpod.hardware")

# Last state we drove the hardware to; read_sensors() reports it back.
state = {
    "ac_running": False,
    "heater_running": False,
    "fan_pct": 0,
}
scent_machine = None  # ScentController, created in setup()


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
    global scent_machine
    log.info("hardware: using STUBS for heater/AC/fan/sensors")
    scent_machine = ScentController()


def cleanup():
    """Put every output in a safe state on exit.

    TODO(hardware): also stop PWM and call GPIO.cleanup().
    """
    set_heater_relay(False)
    set_ac_relay(False)
    set_fan_pwm(0)
    if scent_machine:
        scent_machine.close()
    log.info("hardware: all outputs off")


# --------------------------------------------------------------------------
# Sensors (STUB)
# --------------------------------------------------------------------------
def read_sensors():
    """Return one reading (same fields the HUD's live readouts show).

    TODO(hardware): replace the fake numbers below with real reads, e.g.
        temp_c = dht.temperature; humidity = dht.humidity
        fan_rpm = read_tach_rpm(FAN_TACH_PIN)
    """
    fake_temp_f = 70.0 + random.uniform(-1.5, 1.5)  # noqa: S311 - stub data
    fake_humidity = 45.0 + random.uniform(-3, 3)  # noqa: S311
    fake_rpm = state["fan_pct"] * 30 + random.uniform(-20, 20) if state["fan_pct"] else 0  # noqa: S311

    return {
        "actual_temp_f": round(fake_temp_f, 1),
        "actual_humidity_pct": round(fake_humidity, 1),
        "ac_running": state["ac_running"],
        "heater_running": state["heater_running"],
        "fan_rpm": max(0, round(fake_rpm)),
        "scent_active": scent_machine.active if scent_machine else "none",
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
    scent_machine.apply(
        scent if isinstance(scent, str) else "none",
        to_pct(settings.get("scent_intensity_pct")),
    )

    # TODO(control): target_temp_f / target_humidity_pct are setpoints. If the
    # Pi should run a thermostat loop (rather than the HUD toggling relays
    # manually), compare them against read_sensors() here.
