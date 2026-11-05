"""
XRPod scent machine control. Runs on the Raspberry Pi as part of agent.py.

Hardware model (change the constants below to match your build):
  * One digital output per scent cartridge, driving that cartridge's pump,
    atomizer or valve through a relay or MOSFET. At most one is ever on.
  * One PWM output that sets intensity (atomizer or fan duty cycle).

By default this uses a stub backend that only logs, so the agent runs on any
machine. On the Pi, set SCENT_HARDWARE=gpio to drive real pins (needs the
RPi.GPIO package, which Raspberry Pi OS ships with).

Bench test without the rest of the agent:
    python3 scent.py lavender 60      # lavender at 60% for 10 s, then off
    SCENT_HARDWARE=gpio python3 scent.py pine 100 5
"""

import logging
import os
import sys
import time

log = logging.getLogger("xrpod-agent.scent")

# TODO(hardware): BCM pin numbers for each cartridge output. Keys must match
# SCENTS in store.py ("none" means off and has no pin).
CARTRIDGE_PINS = {
    "lavender": 5,
    "pine": 6,
    "citrus": 13,
    "ocean": 19,
    "rain": 26,
}
# TODO(hardware): PWM pin and frequency for the intensity output.
INTENSITY_PWM_PIN = 18
INTENSITY_PWM_HZ = 1000
# Set to True if your relay board switches on when the pin is LOW.
ACTIVE_LOW = False


class StubBackend:
    """Logs what it would do. Used when there's no real hardware."""

    def setup(self, pins, pwm_pin, pwm_hz):
        log.info("scent: STUB backend (set SCENT_HARDWARE=gpio on the Pi)")

    def set_output(self, pin, on):
        log.debug("scent: pin %s -> %s", pin, "on" if on else "off")

    def set_pwm(self, duty_pct):
        log.debug("scent: pwm -> %s%%", duty_pct)

    def close(self):
        pass


class GPIOBackend:
    """Drives real pins with RPi.GPIO. Not yet tested on the actual pod."""

    def setup(self, pins, pwm_pin, pwm_hz):
        import RPi.GPIO as GPIO  # only available on the Pi

        self.GPIO = GPIO
        GPIO.setmode(GPIO.BCM)
        for pin in pins:
            GPIO.setup(pin, GPIO.OUT, initial=self._level(False))
        GPIO.setup(pwm_pin, GPIO.OUT)
        self.pwm = GPIO.PWM(pwm_pin, pwm_hz)
        self.pwm.start(0)
        self.pins = list(pins) + [pwm_pin]

    def _level(self, on):
        return (not on) if ACTIVE_LOW else on

    def set_output(self, pin, on):
        self.GPIO.output(pin, self._level(on))

    def set_pwm(self, duty_pct):
        self.pwm.ChangeDutyCycle(duty_pct)

    def close(self):
        self.pwm.stop()
        self.GPIO.cleanup(self.pins)


def make_backend():
    if os.environ.get("SCENT_HARDWARE", "").lower() == "gpio":
        return GPIOBackend()
    return StubBackend()


class ScentController:
    """Keeps the scent machine in the requested state, one cartridge at a time."""

    def __init__(self, backend=None):
        self.backend = backend or make_backend()
        self.backend.setup(CARTRIDGE_PINS.values(), INTENSITY_PWM_PIN, INTENSITY_PWM_HZ)
        self.active = "none"
        self.intensity = 0
        self.off()

    def apply(self, scent, intensity_pct):
        """Turn on `scent` at `intensity_pct` (0-100). Unknown scent, "none"
        or 0% intensity all mean off."""
        intensity = max(0, min(100, int(intensity_pct)))
        if scent not in CARTRIDGE_PINS or intensity == 0:
            self.off()
            return
        if (scent, intensity) == (self.active, self.intensity):
            return

        # Break before make: never two cartridges on, even for a moment.
        for name, pin in CARTRIDGE_PINS.items():
            if name != scent:
                self.backend.set_output(pin, False)
        self.backend.set_output(CARTRIDGE_PINS[scent], True)
        self.backend.set_pwm(intensity)
        if scent != self.active:
            log.info("scent: %s at %s%%", scent, intensity)
        self.active, self.intensity = scent, intensity

    def off(self):
        self.backend.set_pwm(0)
        for pin in CARTRIDGE_PINS.values():
            self.backend.set_output(pin, False)
        if self.active != "none":
            log.info("scent: off")
        self.active, self.intensity = "none", 0

    def close(self):
        self.off()
        self.backend.close()


def _bench_test(argv):
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(message)s")
    scent = argv[1] if len(argv) > 1 else "lavender"
    intensity = int(argv[2]) if len(argv) > 2 else 50
    seconds = float(argv[3]) if len(argv) > 3 else 10
    controller = ScentController()
    try:
        controller.apply(scent, intensity)
        time.sleep(seconds)
    finally:
        controller.close()


if __name__ == "__main__":
    _bench_test(sys.argv)
