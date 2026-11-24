
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

from control_arbiter import ControlArbiter
from store import DEFAULT_SETTINGS


def settings_for(mode):
    return {
        **DEFAULT_SETTINGS,
        "control_mode": mode,
    }


def valid_reading():
    return {
        "actual_temp_f": 72,
        "actual_humidity_pct": 45,
    }


def recommendation(active=True):
    return SimpleNamespace(
        active=active,
        environment="forest",
        zone="neutral",
        target_temp_f=70,
        fan_speed_pct=25,
        reason="Forest demonstration profile",
    )


def test_manual_uses_user_settings():
    arbiter = ControlArbiter()
    settings = settings_for("manual")
    settings["fan_speed_pct"] = 40

    result = arbiter.resolve(
        settings,
        recommendation(),
        valid_reading(),
    )

    assert result.source == "user"
    assert result.settings["fan_speed_pct"] == 40
    assert result.authorized is True


def test_auto_uses_ai_recommendation():
    arbiter = ControlArbiter()

    result = arbiter.resolve(
        settings_for("auto"),
        recommendation(),
        valid_reading(),
    )

    assert result.source == "ai"
    assert result.settings["target_temp_f"] == 70
    assert result.settings["fan_speed_pct"] == 25
    assert result.settings["heater_on"] is False
    assert result.settings["ac_on"] is False


def test_auto_without_recommendation_uses_fallback():
    arbiter = ControlArbiter()

    result = arbiter.resolve(
        settings_for("auto"),
        recommendation(active=False),
        valid_reading(),
    )

    assert result.source == "fallback"
    assert result.authorized is False
    assert result.settings["fan_speed_pct"] == 0


def test_invalid_sensor_uses_fallback():
    arbiter = ControlArbiter()

    result = arbiter.resolve(
        settings_for("auto"),
        recommendation(),
        {
            "actual_temp_f": None,
            "actual_humidity_pct": 45,
        },
    )

    assert result.source == "fallback"
    assert result.settings["heater_on"] is False
    assert result.settings["ac_on"] is False


def test_mode_transition():
    arbiter = ControlArbiter()

    auto_result = arbiter.resolve(
        settings_for("auto"),
        recommendation(),
        valid_reading(),
    )

    manual_result = arbiter.resolve(
        settings_for("manual"),
        recommendation(),
        valid_reading(),
    )

    assert auto_result.source == "ai"
    assert manual_result.source == "user"
    assert arbiter.generation == 2


def test_invalid_mode_uses_fallback():
    arbiter = ControlArbiter()

    result = arbiter.resolve(
        settings_for("invalid"),
        recommendation(),
        valid_reading(),
    )

    assert result.source == "fallback"
    assert result.authorized is False
