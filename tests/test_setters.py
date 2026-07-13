"""Tests for legacy HeaterCooler service dispatch."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.homekit_heatercooler.const import CONF_FAN_LANE, FAN_LANE_MANUAL
from custom_components.homekit_heatercooler.type_heatercooler import (
    CHAR_ACTIVE,
    CHAR_COOLING_THRESHOLD_TEMPERATURE,
    CHAR_ROTATION_SPEED,
    CHAR_SWING_MODE,
    HeaterCooler,
)
from homeassistant.components.climate import (
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODES,
    ATTR_SWING_MODE,
    ATTR_SWING_MODES,
    ATTR_TEMPERATURE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_SWING_MODE,
    SERVICE_SET_TEMPERATURE,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_SUPPORTED_FEATURES
from homeassistant.core import HomeAssistant
from tests.common import ENTITY_ID, set_climate


def _accessory(
    hass: HomeAssistant, hk_driver: object, config: dict | None = None
) -> HeaterCooler:
    return HeaterCooler(hass, hk_driver, "Test", ENTITY_ID, 2, config or {})


async def test_rotation_speed_dispatches_after_async_write_lock(
    hass: HomeAssistant, hk_driver: object
) -> None:
    set_climate(
        hass,
        HVACMode.COOL,
        **{
            ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF],
            ATTR_FAN_MODES: ["Auto", "Low", "Mid", "High"],
        },
    )
    accessory = _accessory(hass, hk_driver, {CONF_FAN_LANE: FAN_LANE_MANUAL})
    calls = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_FAN_MODE)

    accessory._set_chars({CHAR_ROTATION_SPEED: 100})
    await hass.async_block_till_done()

    assert calls[-1].data[ATTR_FAN_MODE] == "High"


async def test_rotation_speed_uses_clamped_characteristic_value(
    hass: HomeAssistant, hk_driver: object
) -> None:
    set_climate(
        hass,
        HVACMode.COOL,
        **{
            ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF],
            ATTR_FAN_MODES: ["Auto", "Low", "Mid", "High"],
        },
    )
    accessory = _accessory(hass, hk_driver, {CONF_FAN_LANE: FAN_LANE_MANUAL})
    calls = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_FAN_MODE)

    accessory._set_chars({CHAR_ROTATION_SPEED: 150})
    await hass.async_block_till_done()

    assert calls[-1].data[ATTR_FAN_MODE] == "High"


async def test_temperature_uses_clamped_characteristic_value(
    hass: HomeAssistant, hk_driver: object
) -> None:
    set_climate(
        hass,
        HVACMode.COOL,
        **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]},
    )
    accessory = _accessory(hass, hk_driver)
    calls = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE)

    accessory._set_chars({CHAR_COOLING_THRESHOLD_TEMPERATURE: 100})
    await hass.async_block_till_done()

    assert calls[-1].data[ATTR_TEMPERATURE] == 30


@pytest.mark.parametrize("value", [float("nan"), float("inf"), "invalid"])
async def test_non_finite_temperature_write_is_ignored(
    hass: HomeAssistant, hk_driver: object, value: object
) -> None:
    set_climate(
        hass,
        HVACMode.COOL,
        **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]},
    )
    accessory = _accessory(hass, hk_driver)
    calls = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE)

    accessory._set_chars({CHAR_COOLING_THRESHOLD_TEMPERATURE: value})
    await hass.async_block_till_done()

    assert not calls


async def test_swing_dispatches_only_valid_binary_writes(
    hass: HomeAssistant, hk_driver: object
) -> None:
    set_climate(
        hass,
        HVACMode.COOL,
        **{
            ATTR_SUPPORTED_FEATURES: ClimateEntityFeature.SWING_MODE,
            ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF],
            ATTR_SWING_MODES: ["off", "vertical"],
            ATTR_SWING_MODE: "off",
        },
    )
    accessory = _accessory(hass, hk_driver)
    calls = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_SWING_MODE)

    accessory._set_chars({CHAR_SWING_MODE: 1})
    await hass.async_block_till_done()
    assert calls[-1].data[ATTR_SWING_MODE] == "vertical"

    accessory._set_chars({CHAR_SWING_MODE: 2})
    await hass.async_block_till_done()
    assert len(calls) == 1


async def test_failed_service_write_resyncs_the_accessory(
    hass: HomeAssistant, hk_driver: object
) -> None:
    set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    accessory = _accessory(hass, hk_driver)

    accessory._set_chars({CHAR_ACTIVE: 0})
    await hass.async_block_till_done()

    assert accessory.char_active.value == 1


async def test_fan_state_updates_after_climate_state_change(
    hass: HomeAssistant, hk_driver: object
) -> None:
    set_climate(
        hass,
        HVACMode.COOL,
        **{
            ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF],
            ATTR_FAN_MODES: ["Auto", "Low", "High"],
            ATTR_FAN_MODE: "Low",
            ATTR_HVAC_ACTION: HVACAction.COOLING,
        },
    )
    accessory = _accessory(hass, hk_driver)
    assert accessory.char_speed is not None
    assert accessory.char_speed.value > 0
