"""Shared fan, swing, and temperature helpers for the legacy accessory."""

from collections.abc import Iterable
import math
from typing import Any

from homeassistant.components.climate import (
    ATTR_FAN_MODES,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_SWING_MODES,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_MIDDLE,
    FAN_OFF,
    SWING_BOTH,
    SWING_HORIZONTAL,
    SWING_OFF,
    SWING_ON,
    SWING_VERTICAL,
)
from homeassistant.components.homekit.util import get_min_max, temperature_to_homekit
from homeassistant.core import State
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)

from .const import FAN_LANE_AUTO, FAN_LANE_MANUAL

ORDERED_FAN_SPEEDS = [FAN_LOW, FAN_MIDDLE, FAN_MEDIUM, FAN_HIGH]
ORDERED_AUTO_FAN_SPEEDS = ["low/auto", "mid/auto", "high/auto"]
FAN_MID = "mid"
MANUAL_FAN_SPEEDS = [FAN_LOW, FAN_MID, FAN_MIDDLE, FAN_MEDIUM, FAN_HIGH]
PRE_DEFINED_FAN_MODES = set(ORDERED_FAN_SPEEDS)
SWING_MODE_PREFERRED_ORDER = [SWING_ON, SWING_BOTH, SWING_HORIZONTAL, SWING_VERTICAL]
PRE_DEFINED_SWING_MODES = set(SWING_MODE_PREFERRED_ORDER)
HEAT_COOL_DEADBAND = 5


def as_float(value: Any) -> float | None:
    """Return a finite float, or None for an invalid HomeKit value."""
    if isinstance(value, (int, float)):
        converted = float(value)
        if math.isfinite(converted):
            return converted
    return None


def as_hap_integer(value: Any) -> int | None:
    """Coerce a raw HomeKit enum value as pyhap does for integer chars."""
    if (converted := as_float(value)) is not None:
        return int(converted)
    return None


def _lower_to_original(modes: Iterable[Any]) -> dict[str, str]:
    """Map string modes by lowercase name while preserving their casing."""
    return {mode.lower(): mode for mode in modes if isinstance(mode, str)}


def get_fan_modes_and_speeds(
    attributes: dict[str, Any], fan_lane: str | None = None
) -> tuple[dict[str, str], list[str]]:
    """Return fan modes and ordered slider speeds."""
    fan_modes = _lower_to_original(attributes.get(ATTR_FAN_MODES) or [])

    if fan_lane == FAN_LANE_AUTO:
        ordered = [mode for mode in ORDERED_AUTO_FAN_SPEEDS if mode in fan_modes]
    elif fan_lane == FAN_LANE_MANUAL:
        ordered = [mode for mode in MANUAL_FAN_SPEEDS if mode in fan_modes]
    elif PRE_DEFINED_FAN_MODES.intersection(fan_modes):
        ordered = [mode for mode in ORDERED_FAN_SPEEDS if mode in fan_modes]
    else:
        ordered = []

    if fan_lane is not None and not ordered:
        ordered = [mode for mode in fan_modes if mode != FAN_OFF]
    return fan_modes, ordered


def get_swing_on_mode(attributes: dict[str, Any]) -> str | None:
    """Return the preferred on swing mode, preserving original casing."""
    lower_to_original = _lower_to_original(attributes.get(ATTR_SWING_MODES) or [])
    for swing_mode in SWING_MODE_PREFERRED_ORDER:
        if swing_mode in lower_to_original:
            return lower_to_original[swing_mode]
    return next(
        (
            mode
            for mode_name, mode in lower_to_original.items()
            if mode_name != SWING_OFF
        ),
        None,
    )


def get_swing_off_mode(attributes: dict[str, Any]) -> str:
    """Return the advertised off swing mode."""
    return _lower_to_original(attributes.get(ATTR_SWING_MODES) or []).get(
        SWING_OFF, SWING_OFF
    )


def has_swing_off_mode(attributes: dict[str, Any]) -> bool:
    """Return whether the entity can turn swing off."""
    return SWING_OFF in _lower_to_original(attributes.get(ATTR_SWING_MODES) or [])


def fan_speed_to_mode(
    ordered_fan_speeds: list[str], fan_modes: dict[str, str], speed: int
) -> str:
    """Return the fan mode for a HomeKit rotation speed."""
    speed_key = percentage_to_ordered_list_item(ordered_fan_speeds, speed - 1)
    return fan_modes[speed_key]


def fan_mode_to_speed(ordered_fan_speeds: list[str], fan_mode: Any) -> int | None:
    """Return the HomeKit rotation speed for a fan mode."""
    if (
        not isinstance(fan_mode, str)
        or (fan_mode_lower := fan_mode.lower()) not in ordered_fan_speeds
    ):
        return None
    return ordered_list_item_to_percentage(ordered_fan_speeds, fan_mode_lower)


def is_swing_on(swing_mode: Any) -> bool:
    """Return whether a standard swing mode maps to HomeKit on."""
    return isinstance(swing_mode, str) and swing_mode.lower() in PRE_DEFINED_SWING_MODES


def get_temperature_range_from_state(
    state: State, unit: str, default_min: float, default_max: float
) -> tuple[float, float]:
    """Return HomeKit-safe temperature bounds for a climate state."""
    min_temp = as_float(state.attributes.get(ATTR_MIN_TEMP))
    max_temp = as_float(state.attributes.get(ATTR_MAX_TEMP))
    min_temp = (
        temperature_to_homekit(min_temp, unit) if min_temp is not None else default_min
    )
    max_temp = (
        temperature_to_homekit(max_temp, unit) if max_temp is not None else default_max
    )
    min_temp, max_temp = get_min_max(min_temp, max_temp)

    rounded_min = math.ceil(min_temp * 10) / 10
    rounded_max = math.floor(max_temp * 10) / 10
    if rounded_min <= rounded_max:
        min_temp, max_temp = rounded_min, rounded_max
    min_temp = max(min_temp, 0)
    return min_temp, max(max_temp, min_temp)


def temperature_attribute_to_homekit(state: State, key: str, unit: str) -> float | None:
    """Return a finite state temperature converted to HomeKit units."""
    if (value := as_float(state.attributes.get(key))) is not None:
        return temperature_to_homekit(value, unit)
    return None


def resolve_target_temp_range(
    current_high: float,
    current_low: float,
    new_high: float | None,
    new_low: float | None,
    min_temp: float,
    max_temp: float,
) -> tuple[float, float]:
    """Return ordered, bounded range targets with the required deadband."""
    high = current_high
    low = current_low
    deadband_enforced = False
    if new_high is not None:
        high = new_high
        if high < low:
            low = high - HEAT_COOL_DEADBAND
            deadband_enforced = True
    if new_low is not None:
        low = new_low
        if low > high:
            high = low + HEAT_COOL_DEADBAND
            deadband_enforced = True
    high = min(high, max_temp)
    low = max(low, min_temp)
    if deadband_enforced and high - low < HEAT_COOL_DEADBAND:
        if high >= max_temp:
            low = max(min_temp, high - HEAT_COOL_DEADBAND)
        else:
            high = min(max_temp, low + HEAT_COOL_DEADBAND)
    return high, low
