
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from store import Store, ValidationError


@pytest.fixture
def store(tmp_path):
    database = Store(str(tmp_path / "test_control.db"))
    yield database
    database.close()


def test_manual_mode_accepts_user_controls(store):
    settings, _ = store.update_settings(
        {"fan_speed_pct": 40},
        changed_by="hud"
    )

    assert settings["fan_speed_pct"] == 40


def test_auto_mode_rejects_manual_controls(store):
    store.update_settings({"control_mode": "auto"})

    with pytest.raises(ValidationError):
        store.update_settings(
            {"fan_speed_pct": 80},
            changed_by="hud"
        )


def test_auto_mode_allows_manual_override(store):
    store.update_settings({"control_mode": "auto"})

    settings, _ = store.update_settings(
        {"control_mode": "manual"},
        changed_by="hud"
    )

    assert settings["control_mode"] == "manual"


def test_rejected_request_does_not_change_settings(store):
    store.update_settings({"control_mode": "auto"})

    before = store.get_settings()

    with pytest.raises(ValidationError):
        store.update_settings({"heater_on": True})

    after = store.get_settings()

    assert after == before


def test_mode_change_and_actuator_change_rejected(store):
    with pytest.raises(ValidationError):
        store.update_settings({
            "control_mode": "auto",
            "fan_speed_pct": 75
        })
