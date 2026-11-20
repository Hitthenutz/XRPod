
from dataclasses import dataclass
import math

from store import DEFAULT_SETTINGS, ValidationError, validate_patch


@dataclass(frozen=True)
class ControlDecision:
    mode: str
    source: str
    settings: dict
    reason: str
    authorized: bool
    generation: int = 0


class ControlArbiter:
    def __init__(self):
        self.generation = 0
        self.previous_mode = None

    def resolve(self, settings, recommendation, reading):
        mode = settings.get("control_mode")

        if mode != self.previous_mode:
            self.generation += 1
            self.previous_mode = mode

        if mode == "manual":
            return ControlDecision(
                mode="manual",
                source="user",
                settings=dict(settings),
                reason="Manual control active",
                authorized=True,
                generation=self.generation,
            )

        if mode != "auto":
            return self._safe_decision("Invalid operating mode")

        if not self._valid_reading(reading):
            return self._safe_decision("Invalid sensor readings")

        if recommendation is None or not recommendation.active:
            return self._safe_decision(
                "No valid automatic recommendation"
            )

        patch = {
            "target_temp_f": recommendation.target_temp_f,
            "fan_speed_pct": recommendation.fan_speed_pct,
            "heater_on": False,
            "ac_on": False,
            "selected_scent": "none",
        }

        try:
            clean = validate_patch(patch, DEFAULT_SETTINGS)
        except (ValidationError, TypeError, ValueError):
            return self._safe_decision(
                "Automatic recommendation failed validation"
            )

        effective = {
            **DEFAULT_SETTINGS,
            **clean,
            "control_mode": "auto",
            "selected_environment": recommendation.environment,
        }

        return ControlDecision(
            mode="auto",
            source="ai",
            settings=effective,
            reason=recommendation.reason,
            authorized=True,
            generation=self.generation,
        )

    def _safe_decision(self, reason):
        safe = {
            **DEFAULT_SETTINGS,
            "control_mode": "auto",
            "heater_on": False,
            "ac_on": False,
            "fan_speed_pct": 0,
            "selected_scent": "none",
            "scent_intensity_pct": 0,
        }

        return ControlDecision(
            mode="auto",
            source="fallback",
            settings=safe,
            reason=reason,
            authorized=False,
            generation=self.generation,
        )

    @staticmethod
    def _valid_reading(reading):
        if not isinstance(reading, dict):
            return False

        temperature = reading.get("actual_temp_f")
        humidity = reading.get("actual_humidity_pct")

        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in (temperature, humidity)
        ):
            return False

        return (
            50 <= temperature <= 95
            and 0 <= humidity <= 100
        )
