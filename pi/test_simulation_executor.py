import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from control_arbiter import ControlDecision
from simulation_executor import SimulationExecutor


def make_decision(generation=1):
    return ControlDecision(
        mode="auto",
        source="ai",
        settings={
            "target_temp_f": 70,
            "fan_speed_pct": 25,
        },
        reason="Forest profile",
        authorized=True,
        generation=generation,
    )


def test_auto_updates_simulation():
    executor = SimulationExecutor()

    result = executor.execute(
        make_decision(),
        {"control_mode": "auto"},
        generation=1,
    )

    assert result["accepted"] is True
    assert result["state"]["fan_speed_pct"] == 25


def test_manual_blocks_ai():
    executor = SimulationExecutor()

    result = executor.execute(
        make_decision(),
        {"control_mode": "manual"},
        generation=1,
    )

    assert result["accepted"] is False
    assert result["state"]["fan_speed_pct"] == 0


def test_stale_generation_rejected():
    executor = SimulationExecutor()

    result = executor.execute(
        make_decision(generation=1),
        {"control_mode": "auto"},
        generation=2,
    )

    assert result["accepted"] is False


def test_fallback_rejected():
    executor = SimulationExecutor()

    decision = ControlDecision(
        mode="auto",
        source="fallback",
        settings={},
        reason="VR disconnected",
        authorized=False,
        generation=1,
    )

    result = executor.execute(
        decision,
        {"control_mode": "auto"},
        generation=1,
    )

    assert result["accepted"] is False


def test_invalid_fan_rejected():
    executor = SimulationExecutor()

    decision = make_decision()
    decision.settings["fan_speed_pct"] = 150

    result = executor.execute(
        decision,
        {"control_mode": "auto"},
        generation=1,
    )

    assert result["accepted"] is False