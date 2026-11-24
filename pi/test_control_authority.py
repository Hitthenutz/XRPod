
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent)
)

from control_authority import authorize_user_patch
from store import ValidationError


def test_manual_allows_user_controls():
    settings = {"control_mode": "manual"}

    assert authorize_user_patch(
        {"fan_speed_pct": 40},
        settings
    )


def test_auto_blocks_user_actuator_changes():
    settings = {"control_mode": "auto"}

    with pytest.raises(ValidationError):
        authorize_user_patch(
            {"fan_speed_pct": 40},
            settings
        )


def test_auto_allows_return_to_manual():
    settings = {"control_mode": "auto"}

    assert authorize_user_patch(
        {"control_mode": "manual"},
        settings
    )


def test_auto_allows_environment_selection():
    settings = {"control_mode": "auto"}

    assert authorize_user_patch(
        {"selected_environment": "forest"},
        settings
    )


def test_mode_change_cannot_include_actuator_changes():
    settings = {"control_mode": "manual"}

    with pytest.raises(ValidationError):
        authorize_user_patch(
            {
                "control_mode": "auto",
                "fan_speed_pct": 80
            },
            settings
        )
