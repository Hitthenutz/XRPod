#!/usr/bin/env python3
"""
XRPod Pi agent — runs on the Raspberry Pi 4, NOT part of the web build.

Every POLL_SECONDS it:
  1. reads the pod's sensors,
  2. POSTs the reading to the push-sensor-reading backend function,
  3. fetches the current PodSettings record (what the HUD wants), and
  4. drives the relays / PWM outputs to match, and sends the scent levels to
     the ESP32 scent mixer over serial.

WHAT TO FILL IN
---------------
  APP_DOMAIN    Your deployed site's domain, e.g. "xrpod.base44.app".
  APP_ID        Your Base44 app id (the "id" in base44/.app.jsonc, or run
                `base44 dashboard open` and copy it from the URL). Needed to
                read PodSettings from the entities API.
  PI_AGENT_KEY  Must match the PI_AGENT_KEY secret set with
                `base44 secrets set PI_AGENT_KEY=...`.
  ESP32_PORT    Serial device of the ESP32 scent mixer, e.g. /dev/ttyUSB0
                (USB) or /dev/serial0 (GPIO UART). Leave unset to stub it.
  read_sensors()     Replace the stub with real sensor reads (e.g. a DHT22 /
                     SHT31 for temp+humidity, a tach input for fan RPM).
  set_*_relay(), set_fan_pwm()
                     Replace the stubs with real GPIO relay + PWM calls.

All settings come from environment variables, which is handy for a systemd
unit:

    APP_DOMAIN=xrpod.base44.app APP_ID=... PI_AGENT_KEY=... \
    ESP32_PORT=/dev/ttyUSB0 python3 agent.py

Uses only the Python standard library, so no pip install is required until
you add real sensor/GPIO libraries.

FAIL-SAFE RULES
---------------
  * Settings from the network are sanitized before they touch hardware:
    only a real JSON `true` turns a relay on, percentages are clamped to
    0-100, unknown scents mean "none", and heater + AC never run together.
  * If the backend is unreachable, the last applied settings are kept (and
    re-sent every cycle, which also keeps the ESP32's watchdog fed).
  * On exit (Ctrl+C, `systemctl stop` / SIGTERM, or a crash) every output is
    turned off.
  * The ESP32 turns every diffuser off by itself if it hears nothing from
    the Pi for a few seconds, so a hung Pi or unplugged cable fails safe.
"""

import json
import logging
import math
import os
import random
import select
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("xrpod-agent")


# --------------------------------------------------------------------------
# Configuration — from environment variables. Bad values stop the agent with
# a clear message instead of failing later in a confusing way.
# --------------------------------------------------------------------------
def env_number(name, default, lo, hi):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        sys.exit(f"config error: {name}={raw!r} is not a number")
    if not math.isfinite(value) or not lo <= value <= hi:
        sys.exit(f"config error: {name}={raw!r} must be between {lo} and {hi}")
    return value


def clean_domain(raw):
    """Accept "https://xrpod.base44.app/" as well as "xrpod.base44.app"."""
    domain = raw.strip()
    for prefix in ("https://", "http://"):
        if domain.lower().startswith(prefix):
            domain = domain[len(prefix):]
    return domain.strip("/")


APP_DOMAIN = clean_domain(os.environ.get("APP_DOMAIN", "YOUR-APP.base44.app"))
APP_ID = os.environ.get("APP_ID", "YOUR_APP_ID").strip()
PI_AGENT_KEY = os.environ.get("PI_AGENT_KEY", "CHANGE_ME").strip()

# Lower bound keeps a typo like POLL_SECONDS=0 from hammering the API; upper
# bound must stay well under the ESP32 watchdog (ESP32_WATCHDOG_MS).
POLL_SECONDS = env_number("POLL_SECONDS", 3.0, 1.0, 5.0)
HTTP_TIMEOUT_SECONDS = 10

ESP32_PORT = os.environ.get("ESP32_PORT", "").strip()
ESP32_BAUD = int(env_number("ESP32_BAUD", 115200, 9600, 921600))
ESP32_REPLY_TIMEOUT_SECONDS = 1.0
# Opening a USB serial port usually resets an ESP32 dev board; give it time
# to boot before talking to it.
ESP32_BOOT_SECONDS = 2.0
ESP32_RECONNECT_SECONDS = 10.0

BASE_URL = f"https://{APP_DOMAIN}"
PUSH_READING_URL = f"{BASE_URL}/functions/push-sensor-reading"
# If your domain doesn't route /functions/, the SDK's equivalent path is:
#   f"{BASE_URL}/api/apps/{APP_ID}/functions/push-sensor-reading"
# Oldest PodSettings record is the canonical one (the HUD uses the same rule).
POD_SETTINGS_URL = (
    f"{BASE_URL}/api/apps/{urllib.parse.quote(APP_ID, safe='')}/entities/PodSettings?"
    + urllib.parse.urlencode({"sort": "created_date", "limit": 1})
)

# Mirrors SCENTS in src/lib/podSettings.js, the enum in
# base44/entities/PodSettings.jsonc and SCENT_NAMES in esp32-scent/.
SCENTS = ("none", "lavender", "pine", "citrus", "ocean", "rain")

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

# Plausible sensor ranges; a reading outside them is a sensor fault and is
# not pushed. Keep in sync with READING_RANGES in push-sensor-reading.
TEMP_RANGE_F = (-40.0, 185.0)
HUMIDITY_RANGE_PCT = (0.0, 100.0)

# Last state we drove the hardware to; read_sensors() reports it back.
hardware_state = {
    "ac_running": False,
    "heater_running": False,
    "fan_pct": 0,
    "scent": "none",
}

scent_link = None  # Esp32ScentLink once setup_hardware() runs, if configured


class HardwareError(Exception):
    pass


class SensorError(Exception):
    pass


# --------------------------------------------------------------------------
# ESP32 scent mixer link
# --------------------------------------------------------------------------
class Esp32Error(HardwareError):
    pass


class Esp32ScentLink:
    """Line-based serial link to the ESP32 that drives the scent diffusers.

    Protocol (8N1, ASCII, one command per line, see esp32-scent/):
      Pi -> ESP32   MIX lavender=0 pine=40 citrus=0 ocean=0 rain=0
                    OFF
                    PING
      ESP32 -> Pi   OK
                    ERR <reason>
    Any other line from the ESP32 (boot messages, debug prints) is ignored.

    Uses termios directly so the agent stays stdlib-only (Linux only).
    """

    def __init__(self, port, baud):
        self.port = port
        self.baud = baud
        self.fd = None
        self.buffer = b""
        self.retry_at = 0.0

    def _open(self):
        import termios  # Linux only; imported here so dev machines can stub

        speed = getattr(termios, f"B{self.baud}", None)
        if speed is None:
            raise Esp32Error(f"unsupported baud rate {self.baud}")

        fd = os.open(self.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            attrs = termios.tcgetattr(fd)
            attrs[0] = 0  # iflag: no input processing
            attrs[1] = 0  # oflag: no output processing
            attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL  # 8N1
            attrs[3] = 0  # lflag: raw, no echo
            attrs[4] = attrs[5] = speed
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
            time.sleep(ESP32_BOOT_SECONDS)
            termios.tcflush(fd, termios.TCIOFLUSH)  # drop boot chatter
        except Exception:
            os.close(fd)
            raise
        self.fd = fd
        self.buffer = b""
        log.info("ESP32 scent mixer connected on %s @ %d baud", self.port, self.baud)

    def close(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None

    def _write_all(self, data):
        deadline = time.monotonic() + ESP32_REPLY_TIMEOUT_SECONDS
        while data:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Esp32Error("timed out writing to ESP32")
            _, writable, _ = select.select([], [self.fd], [], remaining)
            if writable:
                data = data[os.write(self.fd, data):]

    def _read_reply(self):
        """Return the next OK/ERR line, skipping anything else."""
        deadline = time.monotonic() + ESP32_REPLY_TIMEOUT_SECONDS
        while True:
            while b"\n" in self.buffer:
                raw, self.buffer = self.buffer.split(b"\n", 1)
                line = raw.decode("ascii", errors="replace").strip()
                if line == "OK" or line.startswith("ERR"):
                    return line
                if line:
                    log.debug("ESP32: %s", line)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Esp32Error("no reply from ESP32 (timeout)")
            readable, _, _ = select.select([self.fd], [], [], remaining)
            if readable:
                chunk = os.read(self.fd, 256)
                if not chunk:
                    raise Esp32Error("ESP32 serial port closed")
                # Cap the buffer so line noise without newlines can't grow it.
                self.buffer = (self.buffer + chunk)[-1024:]

    def command(self, line):
        """Send one command and wait for OK. Raises Esp32Error otherwise."""
        if self.fd is None:
            if time.monotonic() < self.retry_at:
                raise Esp32Error(f"ESP32 offline ({self.port}); will retry")
            try:
                self._open()
            except Exception as err:  # OSError, termios.error, ImportError …
                self.retry_at = time.monotonic() + ESP32_RECONNECT_SECONDS
                raise Esp32Error(f"can't open {self.port}: {err}") from err

        try:
            self._write_all(line.encode("ascii") + b"\n")
            reply = self._read_reply()
        except (OSError, Esp32Error) as err:
            # Unplugged or out of sync: drop the port and reopen next time.
            self.close()
            self.retry_at = time.monotonic() + ESP32_RECONNECT_SECONDS
            if isinstance(err, Esp32Error):
                raise
            raise Esp32Error(f"serial error on {self.port}: {err}") from err

        if reply != "OK":
            raise Esp32Error(f"ESP32 rejected {line!r}: {reply}")


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
    Note: on Pi OS Bookworm, RPi.GPIO doesn't work on a Pi 5; gpiozero/lgpio
    work on both the Pi 4 and Pi 5.
    """
    global scent_link
    log.info("setup_hardware(): using STUBS for relays, fan and sensors")
    if ESP32_PORT:
        scent_link = Esp32ScentLink(ESP32_PORT, ESP32_BAUD)
    else:
        log.info("ESP32_PORT not set: scent mixer is stubbed")


def cleanup_hardware():
    """Put every output in a safe state on exit.

    Each output is switched off independently, so one failure can't leave
    another one running.
    """
    for name, turn_off in (
        ("heater", lambda: set_heater_relay(False)),
        ("AC", lambda: set_ac_relay(False)),
        ("fan", lambda: set_fan_pwm(0)),
        ("scent", lambda: set_scent("none", 0)),
    ):
        try:
            turn_off()
        except Exception as err:
            log.error("cleanup: couldn't turn %s off: %s", name, err)
    if scent_link is not None:
        scent_link.close()
    # TODO(hardware): stop PWM, GPIO.cleanup().
    log.info("cleanup_hardware(): all outputs off")


# --------------------------------------------------------------------------
# Sensors (STUB)
# --------------------------------------------------------------------------
def read_sensors():
    """Return a dict matching the SensorReading entity.

    TODO(hardware): replace the fake numbers below with real reads, e.g.
        temp_c = dht.temperature; humidity = dht.humidity
        fan_rpm = read_tach_rpm(FAN_TACH_PIN)
    DHT22 reads fail or return None fairly often; just let them raise (or
    return None) and this cycle's push is skipped. Keep actual_temp_f and
    actual_humidity_pct — the backend requires them.
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


def check_reading(reading):
    """Raise SensorError if the reading isn't fit to push."""
    if not isinstance(reading, dict):
        raise SensorError(f"read_sensors() returned {type(reading).__name__}, not dict")
    for field, (lo, hi) in (
        ("actual_temp_f", TEMP_RANGE_F),
        ("actual_humidity_pct", HUMIDITY_RANGE_PCT),
    ):
        value = reading.get(field)
        if not is_number(value):
            raise SensorError(f"{field} is {value!r}, not a number")
        if not lo <= value <= hi:
            raise SensorError(f"{field}={value} is outside {lo}..{hi}")
    rpm = reading.get("fan_rpm")
    if rpm is not None and not (is_number(rpm) and rpm >= 0):
        log.warning("dropping bad fan_rpm=%r", rpm)
        reading.pop("fan_rpm")


# --------------------------------------------------------------------------
# Actuators (STUB, except scent when ESP32_PORT is set)
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
    """Send the full mix to the ESP32: the selected scent at intensity_pct,
    every other cartridge at 0. "none" turns every diffuser off."""
    levels = {name: 0 for name in SCENTS if name != "none"}
    if scent in levels:
        levels[scent] = intensity_pct
    active = scent if scent in levels and intensity_pct > 0 else "none"

    if scent_link is None:
        hardware_state["scent"] = active
        return
    try:
        scent_link.command("MIX " + " ".join(f"{k}={v}" for k, v in levels.items()))
    except Esp32Error:
        # We don't know what the diffusers are doing; the ESP32 watchdog
        # turns them off if the link stays down.
        hardware_state["scent"] = "unknown"
        raise
    hardware_state["scent"] = active


# --------------------------------------------------------------------------
# Settings → hardware
# --------------------------------------------------------------------------
def is_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def clamp(value, lo, hi):
    return max(lo, min(hi, value))


def sanitize_settings(raw):
    """Turn an untrusted PodSettings record into safe hardware commands.

    Anything malformed falls back to "off", never to "on".
    """
    if not isinstance(raw, dict):
        raise ValueError(f"PodSettings is {type(raw).__name__}, not an object")

    def pct(field):
        value = raw.get(field)
        if value is None:
            return 0
        if not is_number(value):
            log.warning("bad %s=%r, using 0", field, value)
            return 0
        return clamp(int(round(value)), 0, 100)

    # Only a real JSON true counts; "false", 1 or "yes" never switch a relay.
    heater_on = raw.get("heater_on") is True
    ac_on = raw.get("ac_on") is True
    if heater_on and ac_on:
        # The HUD keeps these exclusive, but never run both on real hardware.
        log.warning("heater_on and ac_on both set — turning both off")
        heater_on = ac_on = False

    scent = raw.get("selected_scent") or "none"
    if scent not in SCENTS:
        log.warning("unknown selected_scent=%r, using 'none'", scent)
        scent = "none"

    return {
        "heater_on": heater_on,
        "ac_on": ac_on,
        "fan_pct": pct("fan_speed_pct"),
        "scent": scent,
        "scent_pct": pct("scent_intensity_pct") if scent != "none" else 0,
    }


def apply_settings(settings):
    """Drive the hardware to match the desired PodSettings.

    Each subsystem is applied independently, so an unplugged ESP32 doesn't
    stop the fan or the heater from following the HUD. Raises HardwareError
    listing every part that failed.
    """
    desired = sanitize_settings(settings)
    errors = []

    try:
        # Always switch the one going off before the one coming on, and stop
        # if that fails, so heater and AC can never both be energized.
        if not desired["heater_on"]:
            set_heater_relay(False)
        if not desired["ac_on"]:
            set_ac_relay(False)
        if desired["heater_on"]:
            set_heater_relay(True)
        if desired["ac_on"]:
            set_ac_relay(True)
    except Exception as err:
        errors.append(f"heater/AC: {err}")
        for turn_off in (set_heater_relay, set_ac_relay):
            try:
                turn_off(False)
            except Exception as off_err:
                errors.append(f"heater/AC fail-safe off: {off_err}")

    try:
        set_fan_pwm(desired["fan_pct"])
    except Exception as err:
        errors.append(f"fan: {err}")

    try:
        set_scent(desired["scent"], desired["scent_pct"])
    except Exception as err:
        errors.append(f"scent: {err}")

    # TODO(control): target_temp_f / target_humidity_pct are setpoints. If the
    # Pi should run a thermostat loop (rather than the HUD toggling relays
    # manually), compare them against read_sensors() here.

    if errors:
        raise HardwareError("; ".join(errors))
    return desired


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
def http_json(method, url, body=None, headers=None):
    # allow_nan=False: NaN/Infinity aren't valid JSON; fail here, clearly.
    data = json.dumps(body, allow_nan=False).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    req.add_header("X-App-Id", APP_ID)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
        raw = resp.read()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError as err:
        snippet = raw[:120].decode(errors="replace")
        raise ValueError(f"response from {url} isn't JSON: {snippet!r}") from err


def push_reading(reading):
    return http_json(
        "POST", PUSH_READING_URL, reading, headers={"x-agent-key": PI_AGENT_KEY}
    )


def fetch_settings():
    records = http_json("GET", POD_SETTINGS_URL)
    if not isinstance(records, list):
        raise ValueError(f"expected a list of PodSettings, got {type(records).__name__}")
    return records[0] if records else None


def describe_error(err):
    if isinstance(err, urllib.error.HTTPError):
        try:
            detail = err.read().decode(errors="replace")[:200]
        except Exception:
            detail = err.reason
        hint = " (check PI_AGENT_KEY)" if err.code in (401, 403) else ""
        return f"HTTP {err.code}{hint}: {detail}"
    if isinstance(err, urllib.error.URLError):
        return f"network error: {err.reason}"
    return f"{type(err).__name__}: {err}"


class FailureLog:
    """Logs the first failure, then every 20th, then the recovery, so a long
    outage doesn't flood the journal (and the Pi's SD card)."""

    def __init__(self, what):
        self.what = what
        self.count = 0

    def failed(self, err):
        self.count += 1
        if self.count == 1 or self.count % 20 == 0:
            log.error("%s failed (%d in a row): %s", self.what, self.count, describe_error(err))

    def ok(self):
        if self.count:
            log.info("%s recovered after %d failure(s)", self.what, self.count)
            self.count = 0


# --------------------------------------------------------------------------
# Main loop
# --------------------------------------------------------------------------
def handle_stop_signal(signum, _frame):
    # systemd stops services with SIGTERM, which would otherwise kill us
    # without running cleanup_hardware().
    raise SystemExit(f"received signal {signum}")


def main():
    level_name = os.environ.get("LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, level_name, None)
    logging.basicConfig(
        level=level if isinstance(level, int) else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if not isinstance(level, int):
        log.warning("unknown LOG_LEVEL=%r, using INFO", level_name)

    placeholders = [
        name
        for name, value, placeholder in (
            ("APP_DOMAIN", APP_DOMAIN, "YOUR-APP.base44.app"),
            ("APP_ID", APP_ID, "YOUR_APP_ID"),
            ("PI_AGENT_KEY", PI_AGENT_KEY, "CHANGE_ME"),
        )
        if not value or value == placeholder
    ]
    if placeholders:
        log.critical("set %s before running the agent", ", ".join(placeholders))
        return 2

    signal.signal(signal.SIGTERM, handle_stop_signal)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, handle_stop_signal)

    push_log = FailureLog("push reading")
    fetch_log = FailureLog("fetch settings")
    apply_log = FailureLog("apply settings")

    desired = DEFAULT_SETTINGS
    last_applied = None

    try:
        setup_hardware()
        while True:
            started = time.monotonic()

            try:
                reading = read_sensors()
                check_reading(reading)
                push_reading(reading)
                push_log.ok()
                log.debug("pushed reading %s", reading)
            except Exception as err:  # keep looping on any failure
                push_log.failed(err)

            try:
                settings = fetch_settings()
                fetch_log.ok()
                if settings is None:
                    log.warning("no PodSettings record yet — open the HUD once to create it")
                else:
                    desired = settings
            except Exception as err:
                # Keep the last applied state; don't flap hardware on a blip.
                fetch_log.failed(err)

            # Re-applied every cycle, even when the fetch failed: this keeps
            # the ESP32 watchdog fed and re-asserts state after a glitch.
            try:
                applied = apply_settings(desired)
                apply_log.ok()
                if applied != last_applied:
                    log.info(
                        "applied: heater=%s ac=%s fan=%s%% scent=%s@%s%% (targets %s°F, %s%% RH)",
                        applied["heater_on"],
                        applied["ac_on"],
                        applied["fan_pct"],
                        applied["scent"],
                        applied["scent_pct"],
                        desired.get("target_temp_f"),
                        desired.get("target_humidity_pct"),
                    )
                    last_applied = applied
            except Exception as err:
                apply_log.failed(err)

            time.sleep(max(0.0, POLL_SECONDS - (time.monotonic() - started)))
    except KeyboardInterrupt:
        log.info("stopping (Ctrl+C)")
    except SystemExit as stop:
        log.info("stopping (%s)", stop.code)
    except BaseException:
        log.critical("agent crashed", exc_info=True)
        raise
    finally:
        cleanup_hardware()
    return 0


if __name__ == "__main__":
    sys.exit(main())
