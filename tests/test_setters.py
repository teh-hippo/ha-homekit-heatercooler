"""Tests for HeaterCooler characteristic setters and state updates."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from custom_components.homekit_heatercooler.climate_util import HC_COOLING, HC_IDLE
from custom_components.homekit_heatercooler.type_heatercooler import (
    CHAR_ACTIVE,
    CHAR_COOLING_THRESHOLD_TEMPERATURE,
    CHAR_HEATING_THRESHOLD_TEMPERATURE,
    HeaterCooler,
)
from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_FAN_MODE,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODES,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_SWING_MODE,
    ATTR_SWING_MODES,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ATTR_TEMPERATURE,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_SWING_MODE,
    SERVICE_SET_TEMPERATURE,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_SUPPORTED_FEATURES
from homeassistant.core import HomeAssistant
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from tests.common import ENTITY_ID, set_climate


def _accessory(hass: HomeAssistant, hk_driver: object) -> HeaterCooler:
    return HeaterCooler(hass, hk_driver, "Test", ENTITY_ID, 2, {})


async def test_active_zero_turns_off(hass: HomeAssistant, hk_driver: object) -> None:
    set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    acc = _accessory(hass, hk_driver)
    with patch.object(acc, "async_call_service") as mock_call:
        acc._set_chars({CHAR_ACTIVE: 0})
    assert mock_call.call_args_list[0][0][1] == "turn_off"


async def test_single_setpoint_temperature_write(
    hass: HomeAssistant, hk_driver: object
) -> None:
    set_climate(
        hass,
        HVACMode.COOL,
        **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF], ATTR_TEMPERATURE: 22},
    )
    acc = _accessory(hass, hk_driver)
    with patch.object(acc, "async_call_service") as mock_call:
        acc._set_chars({CHAR_COOLING_THRESHOLD_TEMPERATURE: 25.0})
    assert mock_call.call_args[0][1] == SERVICE_SET_TEMPERATURE
    data = mock_call.call_args[0][2]
    assert data[ATTR_TEMPERATURE] == 25.0
    assert ATTR_TARGET_TEMP_HIGH not in data
    assert ATTR_TARGET_TEMP_LOW not in data


async def test_dual_setpoint_write_sends_both_thresholds(
    hass: HomeAssistant, hk_driver: object
) -> None:
    # A range entity needs both thresholds; a single write must send both.
    set_climate(
        hass,
        HVACMode.HEAT_COOL,
        **{
            ATTR_HVAC_MODES: [HVACMode.HEAT_COOL, HVACMode.OFF],
            ATTR_TARGET_TEMP_HIGH: 26,
            ATTR_TARGET_TEMP_LOW: 20,
        },
    )
    acc = _accessory(hass, hk_driver)
    with patch.object(acc, "async_call_service") as mock_call:
        acc._set_chars({CHAR_COOLING_THRESHOLD_TEMPERATURE: 28.0})
    data = mock_call.call_args[0][2]
    assert data[ATTR_TARGET_TEMP_HIGH] == 28.0
    assert data[ATTR_TARGET_TEMP_LOW] == 20.0


async def test_fahrenheit_single_setpoint_tie_break_uses_homekit_units(
    hass: HomeAssistant, hk_driver: object
) -> None:
    # In Fahrenheit, the moved-threshold tie-break must compare values in HomeKit units.
    hass.config.units = US_CUSTOMARY_SYSTEM
    set_climate(
        hass,
        HVACMode.HEAT_COOL,
        **{
            ATTR_HVAC_MODES: [HVACMode.HEAT_COOL, HVACMode.OFF],
            ATTR_TEMPERATURE: 72,
            ATTR_MIN_TEMP: 60,
            ATTR_MAX_TEMP: 90,
        },
    )
    acc = _accessory(hass, hk_driver)
    with patch.object(acc, "async_call_service") as mock_call:
        acc._set_chars(
            {
                CHAR_COOLING_THRESHOLD_TEMPERATURE: 25.0,
                CHAR_HEATING_THRESHOLD_TEMPERATURE: 22.0,
            }
        )
    data = mock_call.call_args[0][2]
    assert data[ATTR_TEMPERATURE] == pytest.approx(77.0)


async def test_update_state_reflects_cooling_action(
    hass: HomeAssistant, hk_driver: object
) -> None:
    set_climate(
        hass,
        HVACMode.COOL,
        **{
            ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF],
            ATTR_HVAC_ACTION: HVACAction.COOLING,
            ATTR_CURRENT_TEMPERATURE: 25,
        },
    )
    acc = _accessory(hass, hk_driver)
    assert acc.char_current_state.value == HC_COOLING


async def test_update_state_dry_mode_is_on_and_idle(
    hass: HomeAssistant, hk_driver: object
) -> None:
    """The real daikin reports no action in dry, so HomeKit shows On and Idle."""
    set_climate(
        hass,
        HVACMode.DRY,
        **{
            ATTR_HVAC_MODES: [
                HVACMode.FAN_ONLY,
                HVACMode.DRY,
                HVACMode.COOL,
                HVACMode.HEAT,
                HVACMode.HEAT_COOL,
                HVACMode.OFF,
            ],
            ATTR_CURRENT_TEMPERATURE: 21,
        },
    )
    acc = _accessory(hass, hk_driver)
    assert acc.char_active.value == 1
    assert acc.char_current_state.value == HC_IDLE


async def test_swing_mode_toggle_on(hass: HomeAssistant, hk_driver: object) -> None:
    set_climate(
        hass,
        HVACMode.COOL,
        **{
            ATTR_SUPPORTED_FEATURES: ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.SWING_MODE,
            ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF],
            ATTR_SWING_MODES: ["off", "on"],
            ATTR_SWING_MODE: "off",
        },
    )
    acc = _accessory(hass, hk_driver)
    with patch.object(acc, "async_call_service") as mock_call:
        acc._set_swing_mode(1)
    assert mock_call.call_args[0][1] == SERVICE_SET_SWING_MODE
    assert mock_call.call_args[0][2][ATTR_SWING_MODE] == "on"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "nope"])
async def test_non_finite_temperature_write_is_noop(
    hass: HomeAssistant, hk_driver: object, bad: object
) -> None:
    """A NaN/inf threshold write must be ignored, never sent onward."""
    set_climate(
        hass,
        HVACMode.COOL,
        **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF], ATTR_TEMPERATURE: 22},
    )
    acc = _accessory(hass, hk_driver)
    with patch.object(acc, "async_call_service") as mock_call:
        acc._set_chars({CHAR_COOLING_THRESHOLD_TEMPERATURE: bad})
    assert not mock_call.called


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
async def test_non_finite_fan_speed_write_is_noop(
    hass: HomeAssistant, hk_driver: object, bad: object
) -> None:
    """A NaN/inf rotation-speed write must be ignored, never crash int()."""
    set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    acc = _accessory(hass, hk_driver)
    with patch.object(acc, "async_call_service") as mock_call:
        acc._set_fan_speed(bad)
    assert not mock_call.called


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
async def test_non_finite_swing_write_is_noop(
    hass: HomeAssistant, hk_driver: object, bad: object
) -> None:
    """A NaN/inf swing write must be ignored, never crash int()."""
    set_climate(
        hass,
        HVACMode.COOL,
        **{
            ATTR_SUPPORTED_FEATURES: ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.SWING_MODE,
            ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF],
            ATTR_SWING_MODES: ["off", "on"],
            ATTR_SWING_MODE: "off",
        },
    )
    acc = _accessory(hass, hk_driver)
    with patch.object(acc, "async_call_service") as mock_call:
        acc._set_swing_mode(bad)
    assert not mock_call.called


async def test_single_setpoint_temperature_write_is_clamped(
    hass: HomeAssistant, hk_driver: object
) -> None:
    """A single-setpoint write above the range is clamped to the max temp."""
    set_climate(
        hass,
        HVACMode.COOL,
        **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF], ATTR_TEMPERATURE: 22},
    )
    acc = _accessory(hass, hk_driver)
    with patch.object(acc, "async_call_service") as mock_call:
        acc._set_chars({CHAR_COOLING_THRESHOLD_TEMPERATURE: 100.0})
    assert mock_call.call_args[0][1] == SERVICE_SET_TEMPERATURE
    assert mock_call.call_args[0][2][ATTR_TEMPERATURE] == 30.0


async def test_rotation_speed_above_range_uses_clamped_value(
    hass: HomeAssistant, hk_driver: object
) -> None:
    """An over-range rotation-speed write drives the clamped top fan mode."""
    set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    acc = _accessory(hass, hk_driver)
    top_mode = acc.fan_modes[acc.ordered_fan_speeds[-1]]
    with patch.object(acc, "async_call_service") as mock_call:
        acc._set_fan_speed(150)
    assert mock_call.call_args[0][1] == SERVICE_SET_FAN_MODE
    assert mock_call.call_args[0][2][ATTR_FAN_MODE] == top_mode


async def test_out_of_range_swing_write_is_ignored(
    hass: HomeAssistant, hk_driver: object
) -> None:
    """A swing write outside the boolean 0/1 range is rejected, not treated as on."""
    set_climate(
        hass,
        HVACMode.COOL,
        **{
            ATTR_SUPPORTED_FEATURES: ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.SWING_MODE,
            ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF],
            ATTR_SWING_MODES: ["off", "on"],
            ATTR_SWING_MODE: "off",
        },
    )
    acc = _accessory(hass, hk_driver)
    with patch.object(acc, "async_call_service") as mock_call:
        acc._set_swing_mode(2)
    assert not mock_call.called
