from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ai_controller import AIController


def test_manual_mode_blocks_ai():
    controller = AIController()

    settings = {"control_mode": "manual"}
    reading = {}

    vr_state = {
        "connected": True,
        "environment": "beach",
        "zone_type": "neutral"
    }

    result = controller.recommend(settings, reading, vr_state)

    assert result.active is False


def test_auto_mode_recommends_profile():
    controller = AIController()

    settings = {"control_mode": "auto"}
    reading = {}

    vr_state = {
        "connected": True,
        "environment": "forest",
        "zone_type": "neutral"
    }

    result = controller.recommend(settings, reading, vr_state)

    assert result.active is True
    assert result.target_temp_f == 70
    assert result.fan_speed_pct == 25


def test_stale_vr_disables_ai():
    controller = AIController()

    settings = {"control_mode": "auto"}
    reading = {}

    vr_state = {
        "connected": False,
        "environment": "desert",
        "zone_type": "hot"
    }

    result = controller.recommend(settings, reading, vr_state)

    assert result.active is False


def test_windy_zone_increases_fan():
    controller = AIController()

    settings = {"control_mode": "auto"}
    reading = {}

    vr_state = {
        "connected": True,
        "environment": "beach",
        "zone_type": "windy"
    }

    result = controller.recommend(settings, reading, vr_state)

    assert result.fan_speed_pct == 65
