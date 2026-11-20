
"""
XRPod control authority.

Determines which settings a user is permitted
to change based on the current operating mode.

This module does not execute hardware commands.
"""

from store import ValidationError


ACTUATOR_FIELDS = frozenset({
    "target_temp_f",
    "target_humidity_pct",
    "fan_speed_pct",
    "ac_on",
    "heater_on",
    "selected_scent",
    "scent_intensity_pct",
})


def authorize_user_patch(patch, current_settings):
    """
    Validate user-facing control authority.

    The public settings API is treated as a user
    interface, not as an AI command channel.
    """

    if not isinstance(patch, dict):
        raise ValidationError(
            "Settings patch must be a JSON object"
        )

    mode = current_settings["control_mode"]

    # In AUTO mode, users may still change the mode
    # or select a virtual environment.
    if mode == "auto":
        blocked = ACTUATOR_FIELDS.intersection(patch)

        if blocked:
            raise ValidationError(
                "Manual actuator changes are disabled "
                "while AUTO mode is active"
            )

    # Prevent switching modes and modifying actuator
    # settings in one request.
    if "control_mode" in patch:
        blocked = ACTUATOR_FIELDS.intersection(patch)

        if blocked:
            raise ValidationError(
                "Change the control mode separately "
                "from actuator settings"
            )

    return True
