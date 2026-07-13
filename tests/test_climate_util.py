"""Tests for rebased legacy climate helpers."""

from __future__ import annotations

import pytest

from custom_components.homekit_heatercooler.climate_util import (
    as_float,
    as_hap_integer,
    fan_mode_to_speed,
    fan_speed_to_mode,
    get_fan_modes_and_speeds,
    get_swing_off_mode,
    get_swing_on_mode,
    get_temperature_range_from_state,
    has_swing_off_mode,
    resolve_target_temp_range,
)
from custom_components.homekit_heatercooler.const import FAN_LANE_AUTO, FAN_LANE_MANUAL
from homeassistant.components.climate import (
    ATTR_FAN_MODES,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_SWING_MODES,
)
from homeassistant.core import State

SEVEN_FAN_MODES = ["Auto", "Low", "Mid", "High", "Low/Auto", "Mid/Auto", "High/Auto"]


def test_hap_numeric_coercion_rejects_non_finite_values() -> None:
    assert as_float(3) == 3.0
    assert as_hap_integer(1.9) == 1
    assert as_float("bad") is None
    assert as_hap_integer(float("nan")) is None
    assert as_hap_integer(float("inf")) is None


def test_auto_fan_lane_uses_auto_referenced_speeds() -> None:
    modes, ordered = get_fan_modes_and_speeds(
        {ATTR_FAN_MODES: SEVEN_FAN_MODES}, FAN_LANE_AUTO
    )
    assert ordered == ["low/auto", "mid/auto", "high/auto"]
    assert fan_speed_to_mode(ordered, modes, 1) == "Low/Auto"
    assert fan_mode_to_speed(ordered, "High/Auto") == 100


def test_manual_fan_lane_uses_manual_speeds() -> None:
    modes, ordered = get_fan_modes_and_speeds(
        {ATTR_FAN_MODES: SEVEN_FAN_MODES}, FAN_LANE_MANUAL
    )
    assert ordered == ["low", "mid", "high"]
    assert fan_speed_to_mode(ordered, modes, 100) == "High"


def test_fan_lane_falls_back_to_advertised_custom_modes() -> None:
    modes, ordered = get_fan_modes_and_speeds(
        {ATTR_FAN_MODES: ["Quiet", "Turbo"]}, FAN_LANE_AUTO
    )
    assert ordered == ["quiet", "turbo"]
    assert fan_speed_to_mode(ordered, modes, 1) == "Quiet"


def test_core_default_ignores_custom_fan_modes() -> None:
    _, ordered = get_fan_modes_and_speeds({ATTR_FAN_MODES: ["Quiet", "Turbo"]})
    assert ordered == []


def test_swing_helpers_preserve_vendor_modes() -> None:
    attributes = {ATTR_SWING_MODES: ["Off", "Quiet"]}
    assert has_swing_off_mode(attributes) is True
    assert get_swing_off_mode(attributes) == "Off"
    assert get_swing_on_mode(attributes) == "Quiet"


@pytest.mark.parametrize(
    ("attributes", "expected"),
    [
        ({ATTR_MIN_TEMP: 18, ATTR_MAX_TEMP: 30}, (18.0, 30.0)),
        ({ATTR_MIN_TEMP: -5, ATTR_MAX_TEMP: 25}, (0.0, 25.0)),
        ({ATTR_MIN_TEMP: 30, ATTR_MAX_TEMP: 18}, (18.0, 30.0)),
        ({ATTR_MIN_TEMP: 62, ATTR_MAX_TEMP: 89}, (16.7, 31.6)),
    ],
)
def test_temperature_range_is_safe_and_inward_rounded(
    attributes: dict[str, object], expected: tuple[float, float]
) -> None:
    unit = "°F" if attributes.get(ATTR_MIN_TEMP) == 62 else "°C"
    state = State("climate.test", "cool", attributes)
    assert get_temperature_range_from_state(state, unit, 7, 35) == expected


def test_temperature_range_uses_defaults_for_invalid_bounds() -> None:
    state = State(
        "climate.test",
        "cool",
        {ATTR_MIN_TEMP: float("nan"), ATTR_MAX_TEMP: "bad"},
    )
    assert get_temperature_range_from_state(state, "°C", 7, 35) == (7, 35)


def test_target_range_preserves_deadband_after_bounds() -> None:
    assert resolve_target_temp_range(24, 20, 19, None, 10, 30) == (19, 14)
    assert resolve_target_temp_range(24, 20, None, 28, 16, 30) == (30, 25)
