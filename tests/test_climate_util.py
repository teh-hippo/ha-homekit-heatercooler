"""Unit tests for the driver-agnostic climate_util mapping helpers."""

from __future__ import annotations

import pytest

from custom_components.homekit_heatercooler.climate_util import (
    HC_COOLING,
    HC_HEATING,
    HC_IDLE,
    HC_INACTIVE,
    HC_TARGET_AUTO,
    HC_TARGET_COOL,
    HC_TARGET_HEAT,
    _initial_last_known_mode,
    build_fan_speed_map,
    build_target_state_map,
    current_heater_cooler_state,
    fan_mode_for_percentage,
    hk_target_mode,
    hk_temperature,
    is_active,
    percentage_for_fan_mode,
    plan_active_mode_change,
    resolve_dual_setpoints,
    resolve_swing_mode,
    select_single_setpoint,
    swing_is_enabled,
    swing_is_on,
    temperature_range,
)
from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    SERVICE_SET_HVAC_MODE,
    HVACAction,
    HVACMode,
)
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

AUTO_MAP = build_target_state_map(True, False, True, True)
SEVEN_MODES = ["Auto", "Low", "Mid", "High", "Low/Auto", "Mid/Auto", "High/Auto"]


def test_plan_active_noop_when_no_writes() -> None:
    calls, last = plan_active_mode_change(None, None, False, AUTO_MAP, HVACMode.COOL)
    assert calls == []
    assert last == HVACMode.COOL


def test_plan_active_zero_turns_off() -> None:
    calls, _ = plan_active_mode_change(0, None, True, AUTO_MAP, HVACMode.COOL)
    assert calls == [("turn_off", {})]


def test_plan_power_on_uses_last_known_mode() -> None:
    calls, _ = plan_active_mode_change(1, None, False, AUTO_MAP, HVACMode.HEAT)
    assert calls == [(SERVICE_SET_HVAC_MODE, {ATTR_HVAC_MODE: HVACMode.HEAT})]


def test_plan_power_on_noop_when_already_active() -> None:
    calls, _ = plan_active_mode_change(1, None, True, AUTO_MAP, HVACMode.HEAT)
    assert calls == []


def test_plan_target_mode_sets_and_records() -> None:
    calls, last = plan_active_mode_change(
        1, HC_TARGET_HEAT, True, AUTO_MAP, HVACMode.COOL
    )
    assert calls == [(SERVICE_SET_HVAC_MODE, {ATTR_HVAC_MODE: HVACMode.HEAT})]
    assert last == HVACMode.HEAT


def test_plan_target_mode_unknown_is_ignored() -> None:
    base = build_target_state_map(False, False, True, True)
    calls, last = plan_active_mode_change(1, HC_TARGET_AUTO, True, base, HVACMode.COOL)
    assert calls == []
    assert last == HVACMode.COOL


def test_plan_active_one_with_unknown_target_uses_last_known_mode() -> None:
    # An invalid target value must not block an explicit Active=1 power-on.
    base = build_target_state_map(False, False, True, True)
    calls, last = plan_active_mode_change(1, HC_TARGET_AUTO, False, base, HVACMode.COOL)
    assert calls == [(SERVICE_SET_HVAC_MODE, {ATTR_HVAC_MODE: HVACMode.COOL})]
    assert last == HVACMode.COOL


def test_plan_active_non_finite_target_does_not_raise() -> None:
    # A NaN/inf TargetHeaterCoolerState write must be ignored, not crash int().
    calls, last = plan_active_mode_change(
        None, float("nan"), True, AUTO_MAP, HVACMode.COOL
    )
    assert calls == []
    assert last == HVACMode.COOL
    # A coincident Active=1 power-on still falls back to the last known mode.
    calls, last = plan_active_mode_change(
        1, float("inf"), False, AUTO_MAP, HVACMode.HEAT
    )
    assert calls == [(SERVICE_SET_HVAC_MODE, {ATTR_HVAC_MODE: HVACMode.HEAT})]
    assert last == HVACMode.HEAT


def test_select_single_setpoint_by_mode() -> None:
    assert select_single_setpoint(HVACMode.COOL, 25.0, 20.0, None) == 25.0
    assert select_single_setpoint(HVACMode.HEAT, 25.0, 20.0, None) == 20.0


def test_select_single_setpoint_heat_cool_picks_moved_handle() -> None:
    # The setpoint that moved furthest from the current target is the one written.
    assert select_single_setpoint(HVACMode.HEAT_COOL, 25.0, 20.0, 21.0) == 25.0
    assert select_single_setpoint(HVACMode.HEAT_COOL, 25.0, None, 21.0) == 25.0
    # A legitimate 0.0 current target must be honoured, not treated as absent.
    assert select_single_setpoint(HVACMode.HEAT_COOL, 2.0, 0.5, 0.0) == 2.0


def test_select_single_setpoint_heat_cool_prefers_heating_otherwise() -> None:
    # Both handles moved equally, so the heating handle wins; heating-only also wins.
    assert select_single_setpoint(HVACMode.HEAT_COOL, 22.0, 20.0, 21.0) == 20.0
    assert select_single_setpoint(HVACMode.HEAT_COOL, None, 20.0, None) == 20.0


def test_select_single_setpoint_fallback() -> None:
    assert select_single_setpoint("dry", 25.0, None, None) == 25.0
    assert select_single_setpoint("dry", None, None, None) is None


def test_fan_mode_for_percentage_auto_lane() -> None:
    modes, ordered = build_fan_speed_map(SEVEN_MODES, "auto")
    assert fan_mode_for_percentage(ordered, modes, 100 / len(ordered)) == "Low/Auto"
    assert fan_mode_for_percentage(ordered, modes, 100) == "High/Auto"


def test_fan_mode_for_percentage_manual_lane() -> None:
    modes, ordered = build_fan_speed_map(SEVEN_MODES, "manual")
    assert fan_mode_for_percentage(ordered, modes, 100 / len(ordered)) == "Low"
    assert fan_mode_for_percentage(ordered, modes, 100) == "High"


@pytest.mark.parametrize("bad", [0, -5, 101, "nope"])
def test_fan_mode_for_percentage_rejects_out_of_range(bad: object) -> None:
    modes, ordered = build_fan_speed_map(SEVEN_MODES, "manual")
    assert fan_mode_for_percentage(ordered, modes, bad) is None


def test_fan_mode_for_percentage_no_speeds() -> None:
    assert fan_mode_for_percentage([], {}, 50) is None


def test_fan_off_maps_to_zero_percent() -> None:
    # Fan off is represented by RotationSpeed 0 and excluded from the detents.
    modes, ordered = build_fan_speed_map(["Off", "Low", "High"], "auto")
    assert ordered == ["low", "high"]
    assert fan_mode_for_percentage(ordered, modes, 0) == "Off"
    assert percentage_for_fan_mode(ordered, modes, "Off") == 0.0


def test_percentage_for_fan_mode_round_trip() -> None:
    modes, ordered = build_fan_speed_map(SEVEN_MODES, "auto")
    assert percentage_for_fan_mode(ordered, modes, "High/Auto") == 100.0


def test_percentage_for_off_lane_mode_is_ignored() -> None:
    # A reading from the other lane (or the malformed "0A") must not move the slider.
    modes, ordered = build_fan_speed_map(SEVEN_MODES, "auto")
    assert percentage_for_fan_mode(ordered, modes, "Low") is None
    assert percentage_for_fan_mode(ordered, modes, "0A") is None


def test_resolve_swing_mode() -> None:
    assert resolve_swing_mode(True, ["off", "on"], "on") == "on"
    assert resolve_swing_mode(False, ["off", "on"], "on") == "off"
    assert resolve_swing_mode(False, ["vertical", "horizontal"], "vertical") is None
    assert resolve_swing_mode(False, [], "on") is None


def test_swing_is_on() -> None:
    assert swing_is_on("on") is True
    assert swing_is_on("Both") is True
    assert swing_is_on("off") is False
    assert swing_is_on(None) is False


def test_swing_is_enabled() -> None:
    # A recognised on token is enabled; an off token or None is not.
    assert swing_is_enabled("on") is True
    assert swing_is_enabled("off") is False
    assert swing_is_enabled(None) is False
    # A non-off vendor mode reads as enabled, but only when it is declared.
    assert swing_is_enabled("quiet") is True
    assert swing_is_enabled("quiet", ["off", "quiet"]) is True
    assert swing_is_enabled("quiet", ["off", "loud"]) is False


def test_current_heater_cooler_state() -> None:
    assert current_heater_cooler_state("heat", HVACAction.HEATING) == HC_HEATING
    assert current_heater_cooler_state("cool", HVACAction.COOLING) == HC_COOLING
    assert current_heater_cooler_state("dry", HVACAction.DRYING) == HC_IDLE
    assert current_heater_cooler_state("fan_only", HVACAction.FAN) == HC_IDLE
    assert current_heater_cooler_state("cool", HVACAction.IDLE) == HC_IDLE
    assert current_heater_cooler_state("off", None) == HC_INACTIVE
    assert current_heater_cooler_state("cool", None) == HC_IDLE
    # A stale action must not make an off/unavailable entity look active.
    assert current_heater_cooler_state("off", HVACAction.HEATING) == HC_INACTIVE
    assert (
        current_heater_cooler_state(STATE_UNAVAILABLE, HVACAction.COOLING)
        == HC_INACTIVE
    )
    assert current_heater_cooler_state("cool", "bogus") == HC_INACTIVE


def test_initial_last_known_mode() -> None:
    # A live non-off mode is kept as the power-on mode.
    assert (
        _initial_last_known_mode(
            HVACMode.HEAT, [HVACMode.COOL, HVACMode.HEAT, HVACMode.OFF]
        )
        == HVACMode.HEAT
    )
    # From off/unknown, fall back to a supported direction, preferring Cool then Heat.
    assert (
        _initial_last_known_mode(None, [HVACMode.HEAT, HVACMode.OFF]) == HVACMode.HEAT
    )
    assert (
        _initial_last_known_mode(
            HVACMode.OFF, [HVACMode.COOL, HVACMode.HEAT, HVACMode.OFF]
        )
        == HVACMode.COOL
    )
    assert (
        _initial_last_known_mode(None, [HVACMode.HEAT_COOL, HVACMode.OFF])
        == HVACMode.HEAT_COOL
    )
    assert (
        _initial_last_known_mode(None, [HVACMode.AUTO, HVACMode.OFF]) == HVACMode.AUTO
    )
    assert (
        _initial_last_known_mode(None, [HVACMode.FAN_ONLY, HVACMode.OFF])
        == HVACMode.FAN_ONLY
    )
    assert _initial_last_known_mode(None, [HVACMode.OFF]) == HVACMode.COOL
    assert _initial_last_known_mode(None, []) == HVACMode.COOL


def test_is_active() -> None:
    assert is_active("cool") == 1
    assert is_active("off") == 0
    assert is_active(STATE_UNAVAILABLE) == 0


def test_hk_target_mode() -> None:
    assert hk_target_mode("cool", AUTO_MAP) == HC_TARGET_COOL
    assert hk_target_mode("heat", AUTO_MAP) == HC_TARGET_HEAT
    assert hk_target_mode("auto", AUTO_MAP) == HC_TARGET_AUTO
    assert hk_target_mode(STATE_UNKNOWN, AUTO_MAP) is None
    assert hk_target_mode("frobnicate", AUTO_MAP) is None
    assert hk_target_mode("off", AUTO_MAP) is None
    base = build_target_state_map(False, False, True, True)
    assert hk_target_mode("off", base) is None
    assert hk_target_mode("auto", base) is None


def test_build_fan_speed_map_lanes_and_fallback() -> None:
    _, auto_ordered = build_fan_speed_map(SEVEN_MODES, "auto")
    assert auto_ordered == ["low/auto", "mid/auto", "high/auto"]

    _, manual_ordered = build_fan_speed_map(SEVEN_MODES, "manual")
    assert manual_ordered == ["low", "mid", "high"]

    # A unit with no lane matches falls back to its own fan modes.
    modes, ordered = build_fan_speed_map(["Quiet", "Turbo"], "auto")
    assert ordered == list(modes)


def test_temperature_range_normal_celsius() -> None:
    assert temperature_range({ATTR_MIN_TEMP: 18, ATTR_MAX_TEMP: 30}, "°C") == (
        18.0,
        30.0,
    )


def test_temperature_range_defaults_when_missing() -> None:
    assert temperature_range({}, "°C") == (7.0, 35.0)


def test_temperature_range_rounds_to_half_degree() -> None:
    # 62 °F -> 16.6667 °C rounds to 16.5; 89 °F -> 31.6667 °C rounds to 31.5.
    assert temperature_range({ATTR_MIN_TEMP: 62, ATTR_MAX_TEMP: 89}, "°F") == (
        16.5,
        31.5,
    )


def test_temperature_range_fixes_reversed_bounds() -> None:
    assert temperature_range({ATTR_MIN_TEMP: 30, ATTR_MAX_TEMP: 18}, "°C") == (
        18.0,
        30.0,
    )


def test_temperature_range_clamps_negative_floor() -> None:
    # A negative lower bound crashes the iOS Home app, so it is clamped to zero.
    assert temperature_range({ATTR_MIN_TEMP: -5, ATTR_MAX_TEMP: 25}, "°C") == (
        0.0,
        25.0,
    )


def test_temperature_range_preserves_zero_bound() -> None:
    # A legitimate 0° bound must not be treated as absent.
    assert temperature_range({ATTR_MIN_TEMP: 0, ATTR_MAX_TEMP: 30}, "°C") == (0.0, 30.0)


def test_temperature_range_ignores_non_numeric_bounds() -> None:
    # A malformed bound falls back to the default instead of raising.
    assert temperature_range({ATTR_MIN_TEMP: "unknown", ATTR_MAX_TEMP: None}, "°C") == (
        7.0,
        35.0,
    )


def test_temperature_range_ignores_non_finite_bounds() -> None:
    # NaN/inf bounds must not reach round(); they fall back to the defaults.
    assert temperature_range(
        {ATTR_MIN_TEMP: float("nan"), ATTR_MAX_TEMP: 30}, "°C"
    ) == (7.0, 30.0)
    assert temperature_range(
        {ATTR_MIN_TEMP: 18, ATTR_MAX_TEMP: float("inf")}, "°C"
    ) == (18.0, 35.0)


def test_hk_temperature_ignores_non_finite() -> None:
    # A NaN/inf temperature attribute is ignored rather than propagated.
    assert hk_temperature({"k": float("nan")}, "k", "°C") is None
    assert hk_temperature({"k": float("inf")}, "k", "°C") is None
    assert hk_temperature({"k": 22}, "k", "°C") == 22.0


def test_build_target_state_map_prefers_heat_cool_for_auto() -> None:
    # HomeKit Auto resolves to HEAT_COOL when the entity supports both.
    assert (
        build_target_state_map(True, True, False, False)[HC_TARGET_AUTO]
        == HVACMode.HEAT_COOL
    )
    assert (
        build_target_state_map(False, True, False, False)[HC_TARGET_AUTO]
        == HVACMode.HEAT_COOL
    )
    assert (
        build_target_state_map(True, False, False, False)[HC_TARGET_AUTO]
        == HVACMode.AUTO
    )


def test_resolve_dual_setpoints_passthrough_within_range() -> None:
    assert resolve_dual_setpoints(26.0, 20.0, 26.0, 20.0, 16.0, 30.0) == (26.0, 20.0)


def test_resolve_dual_setpoints_seeds_unwritten_side() -> None:
    # Only cooling written: heating keeps its current value.
    assert resolve_dual_setpoints(27.0, None, 24.0, 20.0, 16.0, 30.0) == (27.0, 20.0)


def test_resolve_dual_setpoints_deadband_when_cooling_crosses_heating() -> None:
    # Drag cooling below heating: heating is pushed down to keep the 5° gap.
    assert resolve_dual_setpoints(19.0, None, 24.0, 22.0, 10.0, 30.0) == (19.0, 14.0)


def test_resolve_dual_setpoints_deadband_when_heating_crosses_cooling() -> None:
    # Drag heating above cooling: cooling is pushed up to keep the 5° gap.
    assert resolve_dual_setpoints(None, 28.0, 24.0, 20.0, 16.0, 30.0) == (30.0, 28.0)


def test_resolve_dual_setpoints_both_written_crossed_anchors_on_heating() -> None:
    # Both written in one PUT and crossed: core anchors on the heating write.
    assert resolve_dual_setpoints(19.0, 24.0, 24.0, 20.0, 10.0, 30.0) == (29.0, 24.0)


def test_resolve_dual_setpoints_clamps_into_range() -> None:
    assert resolve_dual_setpoints(40.0, 5.0, 40.0, 5.0, 16.0, 30.0) == (30.0, 16.0)


def test_resolve_dual_setpoints_preserves_order_after_clamp() -> None:
    # Clamping must never leave the heating threshold above the cooling one.
    assert resolve_dual_setpoints(5.0, None, 24.0, 20.0, 16.0, 30.0) == (16.0, 16.0)
    assert resolve_dual_setpoints(None, 35.0, 24.0, 20.0, 16.0, 30.0) == (30.0, 30.0)


def test_resolve_dual_setpoints_leaves_absent_side_none() -> None:
    # A wholly unwritten side stays None and is not clamped.
    assert resolve_dual_setpoints(None, 22.0, None, 20.0, 16.0, 30.0) == (None, 22.0)
    assert resolve_dual_setpoints(24.0, None, 26.0, None, 16.0, 30.0) == (24.0, None)
