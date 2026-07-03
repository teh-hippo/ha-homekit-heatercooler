"""End-to-end HeaterCooler write tests through the HomeKit setter callback."""

from __future__ import annotations

import pytest
from homeassistant.components.climate import (
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_HVAC_MODE,
    ATTR_HVAC_MODES,
    ATTR_SWING_MODE,
    ATTR_SWING_MODES,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ATTR_TEMPERATURE,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_SWING_MODE,
    SERVICE_SET_TEMPERATURE,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.components.homekit.accessories import HomeDriver
from homeassistant.const import ATTR_ENTITY_ID, ATTR_SUPPORTED_FEATURES
from homeassistant.core import HomeAssistant
from pyhap.const import HAP_REPR_AID, HAP_REPR_CHARS, HAP_REPR_IID, HAP_REPR_VALUE
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.homekit_heatercooler.type_heatercooler import HeaterCooler
from tests.common import ENTITY_ID, set_climate


async def _create_accessory(
    hass: HomeAssistant, hk_driver: HomeDriver, config: dict | None = None
) -> HeaterCooler:
    """Build a HeaterCooler accessory wired to the driver and running."""
    acc = HeaterCooler(hass, hk_driver, "Test", ENTITY_ID, 1, config or {})
    hk_driver.add_accessory(acc)
    acc.run()
    await hass.async_block_till_done()
    return acc


def _write_char(
    hk_driver: HomeDriver, acc: HeaterCooler, char: object, value: object
) -> None:
    """Simulate a HomeKit write to a single characteristic through the driver."""
    hk_driver.set_characteristics(
        {
            HAP_REPR_CHARS: [
                {
                    HAP_REPR_AID: acc.aid,
                    HAP_REPR_IID: char.to_HAP()[HAP_REPR_IID],
                    HAP_REPR_VALUE: value,
                }
            ]
        },
        "mock_addr",
    )


async def test_active_zero_turns_off_via_hap(
    hass: HomeAssistant, hk_driver: HomeDriver
) -> None:
    """Writing Active=0 through HomeKit turns the entity off."""
    set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    await hass.async_block_till_done()
    acc = await _create_accessory(hass, hk_driver)

    call_turn_off = async_mock_service(hass, CLIMATE_DOMAIN, "turn_off")
    _write_char(hk_driver, acc, acc.char_active, 0)
    await hass.async_block_till_done()

    assert call_turn_off
    assert call_turn_off[0].data[ATTR_ENTITY_ID] == ENTITY_ID


async def test_active_one_powers_on_with_last_mode_via_hap(
    hass: HomeAssistant, hk_driver: HomeDriver
) -> None:
    """Writing Active=1 from off restores the last known mode."""
    set_climate(
        hass,
        HVACMode.OFF,
        **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.HEAT, HVACMode.OFF]},
    )
    await hass.async_block_till_done()
    acc = await _create_accessory(hass, hk_driver)

    call_set_hvac_mode = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE)
    _write_char(hk_driver, acc, acc.char_active, 1)
    await hass.async_block_till_done()

    assert call_set_hvac_mode
    assert call_set_hvac_mode[0].data[ATTR_HVAC_MODE] == acc._last_known_mode


async def test_target_state_write_sets_hvac_mode_via_hap(
    hass: HomeAssistant, hk_driver: HomeDriver
) -> None:
    """Writing TargetHeaterCoolerState drives set_hvac_mode."""
    set_climate(
        hass,
        HVACMode.COOL,
        **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.HEAT, HVACMode.OFF]},
    )
    await hass.async_block_till_done()
    acc = await _create_accessory(hass, hk_driver)

    call_set_hvac_mode = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE)
    _write_char(hk_driver, acc, acc.char_target_state, 1)  # Heat
    await hass.async_block_till_done()

    assert call_set_hvac_mode
    assert call_set_hvac_mode[0].data[ATTR_HVAC_MODE] == HVACMode.HEAT
    assert acc._last_known_mode == HVACMode.HEAT


async def test_single_setpoint_write_via_hap(
    hass: HomeAssistant, hk_driver: HomeDriver
) -> None:
    """A threshold write on a single-setpoint entity sends a plain temperature."""
    set_climate(
        hass,
        HVACMode.COOL,
        **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF], ATTR_TEMPERATURE: 22},
    )
    await hass.async_block_till_done()
    acc = await _create_accessory(hass, hk_driver)

    call_set_temperature = async_mock_service(
        hass, CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE
    )
    _write_char(hk_driver, acc, acc.char_cool, 25.0)
    await hass.async_block_till_done()

    assert call_set_temperature
    assert call_set_temperature[0].data[ATTR_TEMPERATURE] == 25.0
    assert ATTR_TARGET_TEMP_HIGH not in call_set_temperature[0].data


async def test_dual_setpoint_write_via_hap(
    hass: HomeAssistant, hk_driver: HomeDriver
) -> None:
    """A threshold write on a range entity sends both thresholds together."""
    set_climate(
        hass,
        HVACMode.HEAT_COOL,
        **{
            ATTR_HVAC_MODES: [HVACMode.HEAT_COOL, HVACMode.OFF],
            ATTR_TARGET_TEMP_HIGH: 26,
            ATTR_TARGET_TEMP_LOW: 20,
        },
    )
    await hass.async_block_till_done()
    acc = await _create_accessory(hass, hk_driver)

    call_set_temperature = async_mock_service(
        hass, CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE
    )
    _write_char(hk_driver, acc, acc.char_cool, 28.0)
    await hass.async_block_till_done()

    assert call_set_temperature
    data = call_set_temperature[0].data
    assert data[ATTR_TARGET_TEMP_HIGH] == 28.0
    assert data[ATTR_TARGET_TEMP_LOW] == 20.0


async def test_fan_speed_write_via_hap(
    hass: HomeAssistant, hk_driver: HomeDriver
) -> None:
    """The lowest slider step reaches the first ordered fan mode."""
    set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    await hass.async_block_till_done()
    acc = await _create_accessory(hass, hk_driver)

    call_set_fan_mode = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_FAN_MODE)
    assert acc.char_speed is not None
    lowest_step = 100 / len(acc.ordered_fan_speeds)
    _write_char(hk_driver, acc, acc.char_speed, lowest_step)
    await hass.async_block_till_done()

    assert call_set_fan_mode
    assert call_set_fan_mode[0].data[ATTR_FAN_MODE] == "Auto"


@pytest.mark.parametrize(
    ("swing_write", "current_mode", "expected_mode"),
    [(1, "off", "on"), (0, "on", "off")],
)
async def test_swing_toggle_via_hap(
    hass: HomeAssistant,
    hk_driver: HomeDriver,
    swing_write: int,
    current_mode: str,
    expected_mode: str,
) -> None:
    """Toggling swing through HomeKit writes the matching climate swing mode."""
    set_climate(
        hass,
        HVACMode.COOL,
        **{
            ATTR_SUPPORTED_FEATURES: ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.SWING_MODE,
            ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF],
            ATTR_FAN_MODES: ["Auto", "Low", "High"],
            ATTR_SWING_MODES: ["off", "on"],
            ATTR_SWING_MODE: current_mode,
        },
    )
    await hass.async_block_till_done()
    acc = await _create_accessory(hass, hk_driver)

    call_set_swing_mode = async_mock_service(
        hass, CLIMATE_DOMAIN, SERVICE_SET_SWING_MODE
    )
    assert acc.char_swing is not None
    _write_char(hk_driver, acc, acc.char_swing, swing_write)
    await hass.async_block_till_done()

    assert call_set_swing_mode
    assert call_set_swing_mode[0].data[ATTR_SWING_MODE] == expected_mode


async def test_active_float_write_coerces_via_hap(
    hass: HomeAssistant, hk_driver: HomeDriver
) -> None:
    """A float Active write reaches the setter as an int (pyhap uint8 coercion)."""
    set_climate(hass, HVACMode.OFF, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    await hass.async_block_till_done()
    acc = await _create_accessory(hass, hk_driver)

    call_set_hvac_mode = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE)
    _write_char(hk_driver, acc, acc.char_active, 1.5)
    await hass.async_block_till_done()

    # pyhap delivers the raw 1.5; the accessory coerces it to Active=1.
    assert call_set_hvac_mode
    assert call_set_hvac_mode[0].data[ATTR_HVAC_MODE] == HVACMode.COOL


async def test_fan_only_float_active_write_uses_last_supported_mode(
    hass: HomeAssistant, hk_driver: HomeDriver
) -> None:
    """A batched float Active write with an unsupported target still powers on."""
    set_climate(
        hass, HVACMode.OFF, **{ATTR_HVAC_MODES: [HVACMode.OFF, HVACMode.FAN_ONLY]}
    )
    await hass.async_block_till_done()
    acc = await _create_accessory(hass, hk_driver)

    call_set_hvac_mode = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE)
    hk_driver.set_characteristics(
        {
            HAP_REPR_CHARS: [
                {
                    HAP_REPR_AID: acc.aid,
                    HAP_REPR_IID: acc.char_target_state.to_HAP()[HAP_REPR_IID],
                    HAP_REPR_VALUE: 2,
                },
                {
                    HAP_REPR_AID: acc.aid,
                    HAP_REPR_IID: acc.char_active.to_HAP()[HAP_REPR_IID],
                    HAP_REPR_VALUE: 1.5,
                },
            ]
        },
        "mock_addr",
    )
    await hass.async_block_till_done()

    # The coerced Active=1 must reach the fallback and power on the only mode.
    assert call_set_hvac_mode
    assert call_set_hvac_mode[0].data[ATTR_HVAC_MODE] == HVACMode.FAN_ONLY
    assert acc._last_known_mode == HVACMode.FAN_ONLY
