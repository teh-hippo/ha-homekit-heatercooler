"""End-to-end HomeKit characteristic write tests."""

from __future__ import annotations

from pyhap.const import HAP_REPR_AID, HAP_REPR_CHARS, HAP_REPR_IID, HAP_REPR_VALUE
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.homekit_heatercooler.type_heatercooler import HeaterCooler
from homeassistant.components.climate import (
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_HVAC_MODE,
    ATTR_HVAC_MODES,
    ATTR_SWING_MODE,
    ATTR_SWING_MODES,
    ATTR_TEMPERATURE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_SWING_MODE,
    SERVICE_SET_TEMPERATURE,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.homekit.accessories import HomeDriver
from homeassistant.const import ATTR_SUPPORTED_FEATURES
from homeassistant.core import HomeAssistant
from tests.common import ENTITY_ID, set_climate


async def _accessory(hass: HomeAssistant, driver: HomeDriver) -> HeaterCooler:
    accessory = HeaterCooler(hass, driver, "Test", ENTITY_ID, 1, {})
    driver.add_accessory(accessory)
    accessory.run()
    await hass.async_block_till_done()
    return accessory


def _write(
    driver: HomeDriver, accessory: HeaterCooler, char: object, value: object
) -> None:
    driver.set_characteristics(
        {
            HAP_REPR_CHARS: [
                {
                    HAP_REPR_AID: accessory.aid,
                    HAP_REPR_IID: char.to_HAP()[HAP_REPR_IID],
                    HAP_REPR_VALUE: value,
                }
            ]
        },
        "mock_addr",
    )


async def test_active_write_reaches_climate_service(
    hass: HomeAssistant, hk_driver: HomeDriver
) -> None:
    set_climate(hass, HVACMode.OFF, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    accessory = await _accessory(hass, hk_driver)
    calls = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE)

    _write(hk_driver, accessory, accessory.char_active, 1.5)
    await hass.async_block_till_done()

    assert calls[-1].data[ATTR_HVAC_MODE] == HVACMode.COOL


async def test_target_write_reaches_climate_service(
    hass: HomeAssistant, hk_driver: HomeDriver
) -> None:
    set_climate(
        hass,
        HVACMode.COOL,
        **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.HEAT, HVACMode.OFF]},
    )
    accessory = await _accessory(hass, hk_driver)
    calls = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE)

    _write(hk_driver, accessory, accessory.char_target_state, 1)
    await hass.async_block_till_done()

    assert calls[-1].data[ATTR_HVAC_MODE] == HVACMode.HEAT


async def test_raw_temperature_write_is_clamped_via_hap(
    hass: HomeAssistant, hk_driver: HomeDriver
) -> None:
    set_climate(
        hass,
        HVACMode.COOL,
        **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]},
    )
    accessory = await _accessory(hass, hk_driver)
    calls = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE)

    _write(
        hk_driver,
        accessory,
        accessory.char_cool,
        100,
    )
    await hass.async_block_till_done()

    assert calls[-1].data[ATTR_TEMPERATURE] == 30
    assert accessory.char_cool.value == 30


async def test_fan_and_swing_writes_reach_climate_services(
    hass: HomeAssistant, hk_driver: HomeDriver
) -> None:
    set_climate(
        hass,
        HVACMode.COOL,
        **{
            ATTR_SUPPORTED_FEATURES: (
                ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.SWING_MODE
            ),
            ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF],
            ATTR_FAN_MODES: ["Auto", "Low", "High"],
            ATTR_SWING_MODES: ["off", "on"],
            ATTR_SWING_MODE: "off",
        },
    )
    accessory = await _accessory(hass, hk_driver)
    fan_calls = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_FAN_MODE)
    swing_calls = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_SWING_MODE)
    assert accessory.char_speed is not None
    assert accessory.char_swing is not None

    _write(hk_driver, accessory, accessory.char_speed, 100)
    _write(hk_driver, accessory, accessory.char_swing, 1)
    await hass.async_block_till_done()

    assert fan_calls[-1].data[ATTR_FAN_MODE] == "High"
    assert swing_calls[-1].data[ATTR_SWING_MODE] == "on"
