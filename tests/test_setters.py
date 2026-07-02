"""Tests for HeaterCooler characteristic setters and state updates."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODES,
    ATTR_SWING_MODE,
    ATTR_SWING_MODES,
    ATTR_TEMPERATURE,
    SERVICE_SET_TEMPERATURE,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_SUPPORTED_FEATURES
from homeassistant.core import HomeAssistant

from custom_components.homekit_heatercooler.climate_util import HC_COOLING
from custom_components.homekit_heatercooler.type_heatercooler import (
    CHAR_ACTIVE,
    CHAR_COOLING_THRESHOLD_TEMPERATURE,
    HeaterCooler,
)
from tests.common import ENTITY_ID, set_climate


def _accessory(hass: HomeAssistant, hk_driver: object) -> HeaterCooler:
    return HeaterCooler(hass, hk_driver, "Test", ENTITY_ID, 2, {})


async def test_active_zero_turns_off(hass: HomeAssistant, hk_driver: object) -> None:
    set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    acc = _accessory(hass, hk_driver)
    with patch.object(acc, "async_call_service") as mock_call:
        acc._set_chars({CHAR_ACTIVE: 0})
    assert mock_call.call_args_list[0][0][1] == "turn_off"


async def test_single_setpoint_temperature_write(hass: HomeAssistant, hk_driver: object) -> None:
    set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF], ATTR_TEMPERATURE: 22})
    acc = _accessory(hass, hk_driver)
    with patch.object(acc, "async_call_service") as mock_call:
        acc._set_chars({CHAR_COOLING_THRESHOLD_TEMPERATURE: 25.0})
    assert mock_call.called
    assert mock_call.call_args[0][1] == SERVICE_SET_TEMPERATURE


async def test_update_state_reflects_cooling_action(hass: HomeAssistant, hk_driver: object) -> None:
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


async def test_swing_mode_toggle_on(hass: HomeAssistant, hk_driver: object) -> None:
    set_climate(
        hass,
        HVACMode.COOL,
        **{
            ATTR_SUPPORTED_FEATURES: ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.SWING_MODE,
            ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF],
            ATTR_SWING_MODES: ["off", "on"],
            ATTR_SWING_MODE: "off",
        },
    )
    acc = _accessory(hass, hk_driver)
    with patch.object(acc, "async_call_service") as mock_call:
        acc._set_swing_mode(1)
    assert mock_call.called
