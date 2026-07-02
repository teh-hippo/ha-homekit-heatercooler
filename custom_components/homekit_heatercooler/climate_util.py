"""Pure climate <-> HomeKit HeaterCooler mapping helpers.

Driver-agnostic: nothing here touches a HomeKit accessory, driver, or
characteristic object, so the logic can be unit-tested directly and reused by
any HeaterCooler front end.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_MIDDLE,
    SERVICE_SET_HVAC_MODE,
    HVACAction,
    HVACMode,
)
from homeassistant.components.homekit.util import temperature_to_homekit
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.util.enum import try_parse_enum
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)

from .const import FAN_LANE_AUTO

# HomeKit CurrentHeaterCoolerState values (per HomeKit spec).
HC_INACTIVE, HC_IDLE, HC_HEATING, HC_COOLING = range(4)
# HomeKit TargetHeaterCoolerState values.
HC_TARGET_AUTO, HC_TARGET_HEAT, HC_TARGET_COOL = range(3)

HC_HASS_TO_HOMEKIT_TARGET = {
    HVACMode.OFF: HC_TARGET_AUTO,
    HVACMode.HEAT: HC_TARGET_HEAT,
    HVACMode.COOL: HC_TARGET_COOL,
    HVACMode.HEAT_COOL: HC_TARGET_AUTO,
    HVACMode.AUTO: HC_TARGET_AUTO,
}
HC_HOMEKIT_TO_HASS_TARGET_BASE = {
    HC_TARGET_HEAT: HVACMode.HEAT,
    HC_TARGET_COOL: HVACMode.COOL,
}
HC_HASS_TO_HOMEKIT_ACTION = {
    HVACAction.OFF: HC_INACTIVE,
    HVACAction.IDLE: HC_IDLE,
    HVACAction.HEATING: HC_HEATING,
    HVACAction.PREHEATING: HC_HEATING,
    HVACAction.COOLING: HC_COOLING,
    HVACAction.DRYING: HC_COOLING,
    HVACAction.FAN: HC_COOLING,
    HVACAction.DEFROSTING: HC_HEATING,
}
MANUAL_FAN_LANE = [FAN_LOW, "mid", FAN_MIDDLE, FAN_MEDIUM, FAN_HIGH]
AUTO_FAN_LANE = ["low/auto", "mid/auto", "high/auto"]
SWING_ON_SET = {"on", "both", "horizontal", "vertical"}

_OFF_STATES = (HVACMode.OFF, STATE_UNAVAILABLE, STATE_UNKNOWN)


def as_float(value: Any) -> float | None:
    """Convert a HomeKit characteristic value to float where possible."""
    if isinstance(value, (int, float)):
        return float(value)
    return None


def hk_temperature(attributes: Mapping[str, Any], key: str, unit: str) -> float | None:
    """Return a temperature attribute converted to HomeKit units."""
    value = attributes.get(key)
    if value is None:
        return None
    return float(temperature_to_homekit(value, unit))


def build_target_state_map(supports_auto: bool, supports_heat_cool: bool) -> dict[int, HVACMode]:
    """Map HomeKit HeaterCooler target states to Home Assistant HVAC modes.

    Auto is only offered when the entity supports AUTO or HEAT_COOL, so HomeKit
    never presents a target the entity cannot honour.
    """
    target_map = dict(HC_HOMEKIT_TO_HASS_TARGET_BASE)
    if supports_auto:
        target_map[HC_TARGET_AUTO] = HVACMode.AUTO
    elif supports_heat_cool:
        target_map[HC_TARGET_AUTO] = HVACMode.HEAT_COOL
    return target_map


def target_state_valid_values(target_map: dict[int, HVACMode]) -> dict[str, int]:
    """Return the HomeKit valid_values for TargetHeaterCoolerState."""
    return {
        name: value
        for name, value in (("Auto", HC_TARGET_AUTO), ("Heat", HC_TARGET_HEAT), ("Cool", HC_TARGET_COOL))
        if value in target_map
    }


def hk_target_mode(state_value: str, target_map: dict[int, HVACMode]) -> int | None:
    """Map a Home Assistant hvac_mode to the HomeKit target state to display."""
    if state_value in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None
    mode = try_parse_enum(HVACMode, state_value)
    if not mode:
        return None
    hk_value = HC_HASS_TO_HOMEKIT_TARGET.get(mode)
    if hk_value is not None and hk_value in target_map:
        return hk_value
    return None


def current_heater_cooler_state(state_value: str, action: HVACAction | None) -> int:
    """Map hvac_action (or the off state) to a HomeKit CurrentHeaterCoolerState."""
    if action:
        return HC_HASS_TO_HOMEKIT_ACTION.get(action, HC_INACTIVE)
    return HC_INACTIVE if state_value in _OFF_STATES else HC_IDLE


def is_active(state_value: str) -> int:
    """Return the HomeKit Active value (1 unless the entity is off/unavailable)."""
    return int(state_value not in _OFF_STATES)


def build_fan_speed_map(fan_modes: list[str], lane: str) -> tuple[dict[str, str], list[str]]:
    """Return the lowercase->original fan map and the ordered slider keys for a lane."""
    modes = {mode.lower(): mode for mode in fan_modes}
    lane_order = AUTO_FAN_LANE if lane == FAN_LANE_AUTO else MANUAL_FAN_LANE
    ordered = [mode for mode in lane_order if mode in modes]
    return modes, ordered or list(modes)


def fan_mode_for_percentage(
    ordered_fan_speeds: list[str],
    fan_modes: Mapping[str, str],
    percentage: Any,
) -> str | None:
    """Map a HomeKit rotation-speed percentage to a climate fan mode."""
    if not ordered_fan_speeds:
        return None
    speed_value = as_float(percentage)
    if speed_value is None or speed_value <= 0 or speed_value > 100:
        return None
    key = percentage_to_ordered_list_item(ordered_fan_speeds, int(speed_value) - 1)
    return fan_modes.get(key, key)


def percentage_for_fan_mode(
    ordered_fan_speeds: list[str],
    fan_modes: Mapping[str, str],
    current_fan_mode: str | None,
) -> float | None:
    """Map the entity's current fan mode to a HomeKit rotation-speed percentage."""
    if not current_fan_mode or current_fan_mode not in fan_modes.values():
        return None
    for ordered_mode in ordered_fan_speeds:
        if fan_modes.get(ordered_mode) == current_fan_mode:
            return ordered_list_item_to_percentage(ordered_fan_speeds, ordered_mode)
    return None


def resolve_swing_mode(swing_enabled: bool, swing_modes: list[str], swing_on_mode: str) -> str:
    """Return the climate swing_mode string for a HomeKit swing toggle."""
    if swing_enabled:
        return swing_on_mode
    off_modes = {"off", "false", "0"}
    return next(
        (mode for mode in swing_modes if mode.lower() in off_modes),
        swing_modes[0] if swing_modes else "off",
    )


def swing_is_on(swing_mode: str | None) -> bool:
    """Return True when a climate swing_mode represents an active swing."""
    return str(swing_mode or "").lower() in SWING_ON_SET


def select_single_setpoint(
    mode: str,
    cooling_temp: float | None,
    heating_temp: float | None,
    current_target: float | None,
) -> float | None:
    """Pick the setpoint to write for a single-setpoint entity."""
    if mode == HVACMode.COOL and cooling_temp is not None:
        return cooling_temp
    if mode == HVACMode.HEAT and heating_temp is not None:
        return heating_temp
    if mode == HVACMode.HEAT_COOL:
        if cooling_temp is not None and heating_temp is not None:
            if current_target and abs(cooling_temp - current_target) > abs(heating_temp - current_target):
                return cooling_temp
            return heating_temp
        if cooling_temp is not None:
            return cooling_temp
        return heating_temp
    if cooling_temp is not None:
        return cooling_temp
    return heating_temp


def plan_active_mode_change(
    active: Any,
    target_mode: Any,
    currently_active: bool,
    target_map: dict[int, HVACMode],
    last_known_mode: HVACMode,
) -> tuple[list[tuple[str, dict[str, Any]]], HVACMode]:
    """Plan climate service calls for Active / TargetHeaterCoolerState writes.

    Returns the service calls to issue and the (possibly updated) last known mode.
    """
    calls: list[tuple[str, dict[str, Any]]] = []
    if active is None and target_mode is None:
        return calls, last_known_mode

    if active == 0:
        calls.append(("turn_off", {}))
        return calls, last_known_mode

    target_mode_int = int(target_mode) if isinstance(target_mode, (int, float)) else None
    if target_mode_int is not None:
        hass_mode = target_map.get(target_mode_int)
        if hass_mode:
            calls.append((SERVICE_SET_HVAC_MODE, {ATTR_HVAC_MODE: hass_mode}))
            last_known_mode = hass_mode
        return calls, last_known_mode

    if active == 1 and not currently_active:
        calls.append((SERVICE_SET_HVAC_MODE, {ATTR_HVAC_MODE: last_known_mode}))
    return calls, last_known_mode
