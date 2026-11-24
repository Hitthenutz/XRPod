
from dataclasses import dataclass, asdict
import threading


@dataclass(frozen=True)
class SimulatedActuatorState:
    target_temp_f: float = 72
    fan_speed_pct: int = 0
    heater_on: bool = False
    ac_on: bool = False
    selected_scent: str = "none"


class SimulationExecutor:
    def __init__(self):
        self._lock = threading.Lock()
        self._state = SimulatedActuatorState()

    def execute(self, decision, current_settings, generation):
        with self._lock:
            mode = current_settings.get("control_mode")

            if mode != "auto":
                return self._stop("Manual mode active")

            if decision.mode != "auto":
                return self._stop("Decision mode mismatch")

            if decision.source != "ai" or not decision.authorized:
                return self._stop("Automatic decision unavailable")

            if decision.generation != generation:
                return self._stop("Outdated decision")

            settings = decision.settings

            temp = settings.get("target_temp_f")
            fan = settings.get("fan_speed_pct")

            if (
                isinstance(temp, bool)
                or not isinstance(temp, (int, float))
                or not 50 <= temp <= 95
                or isinstance(fan, bool)
                or not isinstance(fan, int)
                or not 0 <= fan <= 100
            ):
                return self._stop("Invalid settings")

            self._state = SimulatedActuatorState(
                target_temp_f=temp,
                fan_speed_pct=fan,
                heater_on=False,
                ac_on=False,
                selected_scent="none",
            )

            return {
                "accepted": True,
                "reason": "Simulation updated",
                "state": asdict(self._state),
            }

    def stop(self, reason="Simulation stopped"):
        with self._lock:
            return self._stop(reason)

    def _stop(self, reason):
        self._state = SimulatedActuatorState()

        return {
            "accepted": False,
            "reason": reason,
            "state": asdict(self._state),
        }

    def get_state(self):
        with self._lock:
            return asdict(self._state)
