
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import control_loop
from control_arbiter import ControlArbiter


class StopAfterOne:
    def __init__(self):
        self.calls = 0

    def is_set(self):
        self.calls += 1
        return self.calls > 1


def test_control_loop_publishes_arbiter_decision():
    settings = {
        "control_mode": "auto",
        "fan_speed_pct": 0,
        "heater_on": False,
        "ac_on": False,
    }

    reading = {
        "actual_temp_f": 72,
        "actual_humidity_pct": 45,
    }

    store = Mock()
    store.get_settings.return_value = settings
    store.add_reading.return_value = reading

    hub = Mock()

    vr = Mock()
    vr.latest.return_value = {
        "connected": True,
        "environment": "forest",
        "zone_type": "neutral",
    }

    ai_controller = Mock()
    ai_controller.recommend.return_value = SimpleNamespace(
        active=True,
        environment="forest",
        zone="neutral",
        target_temp_f=70,
        fan_speed_pct=25,
        reason="Forest demonstration profile",
    )

    ml_model = Mock()
    ml_model.predict.return_value = {
        "prediction": "NORMAL",
        "confidence": 0.95,
    }

    arbiter = ControlArbiter()
    wake = Mock()
    stop = StopAfterOne()

    with patch("agent.hardware.apply_settings") as apply:
        control_loop(
            store,
            hub,
            wake,
            stop,
            vr,
            ai_controller,
            ml_model,
            arbiter,
        )

    ai_events = [
        call.args[1]
        for call in hub.publish.call_args_list
        if call.args[0] == "ai"
    ]

    assert len(ai_events) == 1

    event = ai_events[0]

    assert event["control_source"] == "ai"
    assert event["control_authorized"] is True
    assert event["effective_settings"]["fan_speed_pct"] == 25
    assert event["physical_environment"] == "NORMAL"
    assert event["model_confidence"] == 0.95

    assert event["execution_mode"] == "simulation"
    assert event["simulation"]["accepted"] is True
    assert event["simulation"]["state"]["fan_speed_pct"] == 25
    assert event["simulation"]["state"]["target_temp_f"] == 70
    assert event["simulation"]["state"]["heater_on"] is False
    assert event["simulation"]["state"]["ac_on"] is False

    apply.assert_called_once_with(settings)
