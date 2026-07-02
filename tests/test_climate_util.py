"""Unit tests for the driver-agnostic climate_util mapping helpers."""

from __future__ import annotations

import pytest
from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    SERVICE_SET_HVAC_MODE,
    HVACAction,
    HVACMode,
)
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from custom_components.homekit_heatercooler.climate_util import (
    HC_COOLING,
    HC_IDLE,
    HC_INACTIVE,
    HC_TARGET_AUTO,
    HC_TARGET_COOL,
    HC_TARGET_HEAT,
    build_fan_speed_map,
    build_target_state_map,
    current_heater_cooler_state,
    fan_mode_for_percentage,
    hk_target_mode,
    is_active,
    percentage_for_fan_mode,
    plan_active_mode_change,
    resolve_dual_setpoints,
    resolve_swing_mode,
    select_single_setpoint,
    swing_is_on,
    temperature_range,
)

AUTO_MAP = build_target_state_map(True, False)
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
    calls, last = plan_active_mode_change(1, HC_TARGET_HEAT, True, AUTO_MAP, HVACMode.COOL)
    assert calls == [(SERVICE_SET_HVAC_MODE, {ATTR_HVAC_MODE: HVACMode.HEAT})]
    assert last == HVACMode.HEAT


def test_plan_target_mode_unknown_is_ignored() -> None:
    base = build_target_state_map(False, False)
    calls, last = plan_active_mode_change(1, HC_TARGET_AUTO, True, base, HVACMode.COOL)
    assert calls == []
    assert last == HVACMode.COOL


def test_select_single_setpoint_by_mode() -> None:
    assert select_single_setpoint(HVACMode.COOL, 25.0, 20.0, None) == 25.0
    assert select_single_setpoint(HVACMode.HEAT, 25.0, 20.0, None) == 20.0


def test_select_single_setpoint_heat_cool_picks_moved_handle() -> None:
    # The setpoint that moved furthest from the current target is the one written.
    assert select_single_setpoint(HVACMode.HEAT_COOL, 25.0, 20.0, 21.0) == 25.0
    assert select_single_setpoint(HVACMode.HEAT_COOL, 25.0, None, 21.0) == 25.0


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
    assert resolve_swing_mode(False, ["swing", "spin"], "swing") == "swing"
    assert resolve_swing_mode(False, [], "on") == "off"


def test_swing_is_on() -> None:
    assert swing_is_on("on") is True
    assert swing_is_on("Both") is True
    assert swing_is_on("off") is False
    assert swing_is_on(None) is False


def test_current_heater_cooler_state() -> None:
    assert current_heater_cooler_state("cool", HVACAction.COOLING) == HC_COOLING
    assert current_heater_cooler_state("off", None) == HC_INACTIVE
    assert current_heater_cooler_state("cool", None) == HC_IDLE
    assert current_heater_cooler_state("cool", "bogus") == HC_INACTIVE


def test_is_active() -> None:
    assert is_active("cool") == 1
    assert is_active("off") == 0
    assert is_active(STATE_UNAVAILABLE) == 0


def test_hk_target_mode() -> None:
    assert hk_target_mode("cool", AUTO_MAP) == HC_TARGET_COOL
    assert hk_target_mode("heat", AUTO_MAP) == HC_TARGET_HEAT
    assert hk_target_mode("auto", AUTO_MAP) == HC_TARGET_AUTO
    assert hk_target_mode(STATE_UNKNOWN, AUTO_MAP) is None
    base = build_target_state_map(False, False)
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
    assert temperature_range({ATTR_MIN_TEMP: 18, ATTR_MAX_TEMP: 30}, "°C") == (18.0, 30.0)


def test_temperature_range_defaults_when_missing() -> None:
    assert temperature_range({}, "°C") == (7.0, 35.0)


def test_temperature_range_rounds_to_half_degree() -> None:
    # 62 °F -> 16.6667 °C rounds to 16.5; 89 °F -> 31.6667 °C rounds to 31.5.
    assert temperature_range({ATTR_MIN_TEMP: 62, ATTR_MAX_TEMP: 89}, "°F") == (16.5, 31.5)


def test_temperature_range_fixes_reversed_bounds() -> None:
    assert temperature_range({ATTR_MIN_TEMP: 30, ATTR_MAX_TEMP: 18}, "°C") == (18.0, 30.0)


def test_temperature_range_clamps_negative_floor() -> None:
    # A negative lower bound crashes the iOS Home app, so it is clamped to zero.
    assert temperature_range({ATTR_MIN_TEMP: -5, ATTR_MAX_TEMP: 25}, "°C") == (0.0, 25.0)


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
