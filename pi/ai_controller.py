
from dataclasses import dataclass


@dataclass
class AIRecommendation:
    environment: str
    zone: str
    fan_speed_pct: int
    target_temp_f: float
    reason: str
    active: bool


class AIController:
    """
    Initial XRPod automatic-control policy.

    This version uses explicit rules rather than the
    trained ML model. It is recommendation-only.
    """

    def recommend(self, settings, reading, vr_state):

        # Manual mode: never request automatic control.
        if settings["control_mode"] != "auto":
            return AIRecommendation(
                environment="none",
                zone="neutral",
                fan_speed_pct=0,
                target_temp_f=72,
                reason="Manual mode enabled",
                active=False
            )

        # Missing or stale VR state: do not automate.
        if not vr_state or not vr_state.get("connected"):
            return AIRecommendation(
                environment="none",
                zone="neutral",
                fan_speed_pct=0,
                target_temp_f=72,
                reason="VR state unavailable or stale",
                active=False
            )

        environment = vr_state["environment"]
        zone = vr_state["zone_type"]

        # Demonstration profiles only.
        profiles = {
            "beach": {"temp": 76, "fan": 45},
            "forest": {"temp": 70, "fan": 25},
            "desert": {"temp": 80, "fan": 20},
            "sponsor": {"temp": 72, "fan": 15},
        }

        if environment not in profiles:
            return AIRecommendation(
                environment=environment,
                zone=zone,
                fan_speed_pct=0,
                target_temp_f=72,
                reason="No active environment selected",
                active=False
            )

        profile = profiles[environment]
        fan = profile["fan"]

        if zone == "windy":
            fan = min(100, fan + 20)

        return AIRecommendation(
            environment=environment,
            zone=zone,
            fan_speed_pct=fan,
            target_temp_f=profile["temp"],
            reason=f"Demo profile for {environment}/{zone}",
            active=True
        )
