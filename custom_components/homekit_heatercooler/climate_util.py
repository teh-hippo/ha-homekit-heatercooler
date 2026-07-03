"""Pure climate <-> HomeKit HeaterCooler mapping helpers.

Driver-agnostic: nothing here touches a HomeKit accessory, driver, or
characteristic object, so the logic can be unit-tested directly and reused by
any HeaterCooler front end.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import math
from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_MIDDLE,
    FAN_OFF,
    SERVICE_SET_HVAC_MODE,
    SWING_BOTH,
    SWING_HORIZONTAL,
    SWING_OFF,
    SWING_ON,
    SWING_VERTICAL,
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

# HomeKit RotationSpeed percentage maximum.
HK_MAX_ROTATION_SPEED = 100

HC_HASS_TO_HOMEKIT_TARGET = {
    HVACMode.HEAT: HC_TARGET_HEAT,
    HVACMode.COOL: HC_TARGET_COOL,
    HVACMode.HEAT_COOL: HC_TARGET_AUTO,
    HVACMode.AUTO: HC_TARGET_AUTO,
}
HC_HASS_TO_HOMEKIT_ACTION = {
    HVACAction.OFF: HC_INACTIVE,
    HVACAction.IDLE: HC_IDLE,
    HVACAction.HEATING: HC_HEATING,
    HVACAction.PREHEATING: HC_HEATING,
    HVACAction.COOLING: HC_COOLING,
    HVACAction.DRYING: HC_IDLE,
    HVACAction.FAN: HC_IDLE,
    HVACAction.DEFROSTING: HC_HEATING,
}
FAN_MID = "mid"  # Common vendor alias between LOW and MIDDLE.
MANUAL_FAN_LANE = [FAN_LOW, FAN_MID, FAN_MIDDLE, FAN_MEDIUM, FAN_HIGH]
AUTO_FAN_LANE = ["low/auto", "mid/auto", "high/auto"]
SWING_ON_SET = {SWING_ON, SWING_BOTH, SWING_HORIZONTAL, SWING_VERTICAL}
SWING_OFF_SET = {SWING_OFF, "false", "0"}

# Keep the cooling/heating pair this far apart (HomeKit °C) when a write crosses them.
HEAT_COOL_DEADBAND = 5.0

_OFF_STATES = (HVACMode.OFF, STATE_UNAVAILABLE, STATE_UNKNOWN)


def as_float(value: Any) -> float | None:
    """Convert a HomeKit characteristic value to a finite float where possible.

    Non-numeric values and the non-finite floats HomeKit clients can send
    (NaN, ±inf) return None so callers treat them as "no usable value" rather
    than propagating them into arithmetic or service calls.
    """
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def as_hap_integer(value: Any) -> int | None:
    """Convert a HomeKit numeric enum value using pyhap's integer coercion.

    pyhap delivers the raw client value to a service setter (a uint8 char can
    arrive as a float), so integer-valued characteristics must be coerced here
    before they are compared, exactly as the characteristic itself would.
    """
    float_value = as_float(value)
    if float_value is None:
        return None
    return int(float_value)


def hk_temperature(attributes: Mapping[str, Any], key: str, unit: str) -> float | None:
    """Return a temperature attribute converted to HomeKit units."""
    value = as_float(attributes.get(key))
    if value is None:
        return None
    return float(temperature_to_homekit(value, unit))


def _homekit_bound(raw: Any, unit: str, default: float) -> float:
    """Round a raw temperature bound to the half-degree grid, or use the default."""
    value = as_float(raw)
    if value is None:
        return default
    return round(temperature_to_homekit(value, unit) * 2) / 2


def temperature_range(
    attributes: Mapping[str, Any],
    unit: str,
    default_min: float = DEFAULT_MIN_TEMP,
    default_max: float = DEFAULT_MAX_TEMP,
) -> tuple[float, float]:
    """Return the HeaterCooler threshold min/max for a climate entity.

    Round to HomeKit's half-degree grid, correct a reversed range, and clamp
    the floor to zero (a negative bound crashes the iOS Home app).
    """
    min_temp = _homekit_bound(attributes.get(ATTR_MIN_TEMP), unit, default_min)
    max_temp = _homekit_bound(attributes.get(ATTR_MAX_TEMP), unit, default_max)
    min_temp, max_temp = min(min_temp, max_temp), max(min_temp, max_temp)
    min_temp = max(min_temp, 0.0)
    max_temp = max(max_temp, min_temp)
    return min_temp, max_temp


def _initial_last_known_mode(
    current_mode: HVACMode | None,
    hvac_modes: Iterable[Any],
) -> HVACMode:
    """Return a supported mode to use when HomeKit powers the entity on."""
    if current_mode and current_mode != HVACMode.OFF:
        return current_mode

    supported_modes: list[HVACMode] = []
    for raw_mode in hvac_modes:
        mode = try_parse_enum(HVACMode, raw_mode)
        if mode and mode != HVACMode.OFF and mode not in supported_modes:
            supported_modes.append(mode)

    for preferred_mode in (
        HVACMode.COOL,
        HVACMode.HEAT,
        HVACMode.HEAT_COOL,
        HVACMode.AUTO,
    ):
        if preferred_mode in supported_modes:
            return preferred_mode

    return supported_modes[0] if supported_modes else HVACMode.COOL


def resolve_dual_setpoints(
    cooling: float | None,
    heating: float | None,
    current_cooling: float | None,
    current_heating: float | None,
    min_temp: float,
    max_temp: float,
) -> tuple[float | None, float | None]:
    """Resolve HeaterCooler threshold writes into clamped high/low setpoints.

    Seed each side from its current value, apply the written thresholds in
    cooling-then-heating order, hold the pair a deadband apart when a write
    crosses them, then clamp both into the advertised range.
    """
    high = current_cooling
    low = current_heating
    if cooling is not None:
        high = cooling
        if low is not None and high < low:
            low = high - HEAT_COOL_DEADBAND
    if heating is not None:
        low = heating
        if high is not None and low > high:
            high = low + HEAT_COOL_DEADBAND
    if high is not None:
        high = min(max(high, min_temp), max_temp)
    if low is not None:
        low = min(max(low, min_temp), max_temp)
    if high is not None and low is not None:
        low = min(low, high)
    return high, low


def build_target_state_map(
    supports_auto: bool,
    supports_heat_cool: bool,
    supports_heat: bool,
    supports_cool: bool,
) -> dict[int, HVACMode]:
    """Map HomeKit HeaterCooler target states to Home Assistant HVAC modes.

    Heat and Cool are offered only in the directions the entity supports, and
    Auto only when the entity supports AUTO or HEAT_COOL, so HomeKit never
    presents a target the entity cannot honour. Cool is the fallback when the
    entity advertises none of these, since a HeaterCooler needs one target.
    """
    target_map: dict[int, HVACMode] = {}
    if supports_heat:
        target_map[HC_TARGET_HEAT] = HVACMode.HEAT
    if supports_cool:
        target_map[HC_TARGET_COOL] = HVACMode.COOL
    if supports_heat_cool:
        # Prefer HEAT_COOL for the HomeKit Auto target: it holds a heat/cool
        # range, matching HomeKit's heat-or-cool-to-target semantics.
        target_map[HC_TARGET_AUTO] = HVACMode.HEAT_COOL
    elif supports_auto:
        target_map[HC_TARGET_AUTO] = HVACMode.AUTO
    if not target_map:
        target_map[HC_TARGET_COOL] = HVACMode.COOL
    return target_map


def target_state_valid_values(target_map: dict[int, HVACMode]) -> dict[str, int]:
    """Return the HomeKit valid_values for TargetHeaterCoolerState."""
    return {
        name: value
        for name, value in (
            ("Auto", HC_TARGET_AUTO),
            ("Heat", HC_TARGET_HEAT),
            ("Cool", HC_TARGET_COOL),
        )
        if value in target_map
    }


def hk_target_mode(state_value: str, target_map: dict[int, HVACMode]) -> int | None:
    """Map a Home Assistant hvac_mode to the HomeKit target state to display."""
    if state_value in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None
    mode = try_parse_enum(HVACMode, state_value)
    if not mode:
        return None
    if mode == HVACMode.OFF:
        return None
    hk_value = HC_HASS_TO_HOMEKIT_TARGET.get(mode)
    if hk_value is not None and hk_value in target_map:
        return hk_value
    return None


def current_heater_cooler_state(state_value: str, action: HVACAction | None) -> int:
    """Map hvac_action (or the off state) to a HomeKit CurrentHeaterCoolerState."""
    if state_value in _OFF_STATES:
        return HC_INACTIVE
    if action:
        return HC_HASS_TO_HOMEKIT_ACTION.get(action, HC_INACTIVE)
    return HC_IDLE


def is_active(state_value: str) -> int:
    """Return the HomeKit Active value (1 unless the entity is off/unavailable)."""
    return int(state_value not in _OFF_STATES)


def build_fan_speed_map(
    fan_modes: list[str], lane: str
) -> tuple[dict[str, str], list[str]]:
    """Return the lowercase->original fan map and the ordered slider keys for a lane."""
    modes = {mode.lower(): mode for mode in fan_modes}
    lane_order = AUTO_FAN_LANE if lane == FAN_LANE_AUTO else MANUAL_FAN_LANE
    ordered = [mode for mode in lane_order if mode in modes]
    return modes, ordered or [mode for mode in modes if mode != FAN_OFF]


def fan_mode_for_percentage(
    ordered_fan_speeds: list[str],
    fan_modes: Mapping[str, str],
    percentage: Any,
) -> str | None:
    """Map a HomeKit rotation-speed percentage to a climate fan mode."""
    speed_value = as_float(percentage)
    if speed_value is None or speed_value < 0 or speed_value > HK_MAX_ROTATION_SPEED:
        return None
    if speed_value == 0:
        return fan_modes.get(FAN_OFF)
    if not ordered_fan_speeds:
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
    if current_fan_mode.lower() == FAN_OFF and FAN_OFF in fan_modes:
        return 0.0
    for ordered_mode in ordered_fan_speeds:
        if fan_modes.get(ordered_mode) == current_fan_mode:
            return ordered_list_item_to_percentage(ordered_fan_speeds, ordered_mode)
    return None


def resolve_swing_mode(
    swing_enabled: bool, swing_modes: list[str], swing_on_mode: str
) -> str | None:
    """Return the climate swing_mode string for a HomeKit swing toggle."""
    if swing_enabled:
        return swing_on_mode
    return next((mode for mode in swing_modes if swing_is_off(mode)), None)


def swing_is_on(swing_mode: str | None) -> bool:
    """Return True when a climate swing_mode represents an active swing."""
    return str(swing_mode or "").lower() in SWING_ON_SET


def swing_is_off(swing_mode: str | None) -> bool:
    """Return True when a climate swing_mode represents inactive swing."""
    return str(swing_mode or "").lower() in SWING_OFF_SET


def swing_is_enabled(
    swing_mode: str | None, swing_modes: Iterable[str] | None = None
) -> bool:
    """Return True when a swing mode should read as enabled in HomeKit.

    A recognised on token is enabled and an off token is not; any other
    non-empty mode is treated as enabled when it is one the entity declares.
    """
    if swing_is_on(swing_mode):
        return True
    if swing_mode is None or swing_is_off(swing_mode):
        return False
    if swing_modes is None:
        return True
    swing_mode_lower = str(swing_mode).lower()
    return any(str(mode).lower() == swing_mode_lower for mode in swing_modes)


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
            if current_target is not None and abs(cooling_temp - current_target) > abs(
                heating_temp - current_target
            ):
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

    active_int = as_hap_integer(active)
    if active_int == 0:
        calls.append(("turn_off", {}))
        return calls, last_known_mode

    target_mode_int = as_hap_integer(target_mode)
    if target_mode_int is not None:
        hass_mode = target_map.get(target_mode_int)
        if hass_mode:
            calls.append((SERVICE_SET_HVAC_MODE, {ATTR_HVAC_MODE: hass_mode}))
            last_known_mode = hass_mode
        elif active_int == 1 and not currently_active:
            calls.append((SERVICE_SET_HVAC_MODE, {ATTR_HVAC_MODE: last_known_mode}))
        return calls, last_known_mode

    if active_int == 1 and not currently_active:
        calls.append((SERVICE_SET_HVAC_MODE, {ATTR_HVAC_MODE: last_known_mode}))
    return calls, last_known_mode
