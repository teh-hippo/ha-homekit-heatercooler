"""Tests for the rebased legacy HeaterCooler accessory."""

from __future__ import annotations

import asyncio

import pytest
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.homekit_heatercooler.const import (
    CONF_FAN_ENTITY_ID,
    CONF_FAN_LANE,
    FAN_LANE_AUTO,
    FAN_LANE_MANUAL,
    SERV_HEATER_COOLER,
    SERV_HUMIDITY_SENSOR,
)
from custom_components.homekit_heatercooler.type_heatercooler import (
    CHAR_ACTIVE,
    CHAR_COOLING_THRESHOLD_TEMPERATURE,
    CHAR_HEATING_THRESHOLD_TEMPERATURE,
    CHAR_ROTATION_SPEED,
    CHAR_TARGET_HEATER_COOLER_STATE,
    HC_COOLING,
    HC_IDLE,
    HC_INACTIVE,
    HC_TARGET_COOL,
    HC_TARGET_HEAT,
    HeaterCooler,
)
from homeassistant.components.climate import (
    ATTR_CURRENT_HUMIDITY,
    ATTR_CURRENT_TEMPERATURE,
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_HVAC_MODES,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_SWING_MODE,
    ATTR_SWING_MODES,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ATTR_TEMPERATURE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.fan import (
    ATTR_PERCENTAGE,
    ATTR_PERCENTAGE_STEP,
    DOMAIN as FAN_DOMAIN,
    SERVICE_SET_PERCENTAGE,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    SERVICE_TURN_OFF,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, ServiceCall, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from tests.common import ENTITY_ID, set_climate

SEVEN_FAN_MODES = ["Auto", "Low", "Mid", "High", "Low/Auto", "Mid/Auto", "High/Auto"]


def _accessory(
    hass: HomeAssistant, hk_driver: object, config: dict | None = None
) -> HeaterCooler:
    return HeaterCooler(hass, hk_driver, "Test", ENTITY_ID, 2, config or {})


async def test_basic_accessory_exposes_core_characteristics(
    hass: HomeAssistant, hk_driver: object
) -> None:
    set_climate(
        hass,
        HVACMode.COOL,
        **{
            ATTR_HVAC_MODES: [HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF],
            ATTR_CURRENT_TEMPERATURE: 22,
        },
    )
    accessory = _accessory(hass, hk_driver)

    assert accessory.char_active.value == 1
    assert accessory.char_current_state.value == HC_IDLE
    assert accessory.char_target_state.value == HC_TARGET_COOL
    assert accessory.char_cool.value == 22
    assert accessory.get_service(SERV_HEATER_COOLER).is_primary_service is True


async def test_cool_and_heat_only_entities_expose_one_threshold(
    hass: HomeAssistant, hk_driver: object
) -> None:
    set_climate(
        hass,
        HVACMode.COOL,
        **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]},
    )
    cool_only = _accessory(hass, hk_driver)
    assert hasattr(cool_only, "char_cool")
    assert not hasattr(cool_only, "char_heat")

    set_climate(
        hass,
        HVACMode.HEAT,
        **{ATTR_HVAC_MODES: [HVACMode.HEAT, HVACMode.OFF]},
    )
    heat_only = _accessory(hass, hk_driver)
    assert not hasattr(heat_only, "char_cool")
    assert hasattr(heat_only, "char_heat")


async def test_legacy_fan_lanes_keep_rotation_speed_on_heatercooler(
    hass: HomeAssistant, hk_driver: object
) -> None:
    set_climate(
        hass,
        HVACMode.COOL,
        **{
            ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF],
            ATTR_FAN_MODES: SEVEN_FAN_MODES,
        },
    )
    auto = _accessory(hass, hk_driver, {CONF_FAN_LANE: FAN_LANE_AUTO})
    manual = _accessory(hass, hk_driver, {CONF_FAN_LANE: FAN_LANE_MANUAL})

    assert auto.ordered_fan_speeds == ["low/auto", "mid/auto", "high/auto"]
    assert manual.ordered_fan_speeds == ["low", "mid", "high"]
    assert auto.char_speed is not None


@pytest.mark.parametrize(
    ("mode", "action"),
    [
        (HVACMode.DRY, HVACAction.DRYING),
        (HVACMode.FAN_ONLY, HVACAction.FAN),
    ],
)
async def test_legacy_dry_and_fan_are_active_idle(
    hass: HomeAssistant,
    hk_driver: object,
    mode: HVACMode,
    action: HVACAction,
) -> None:
    set_climate(
        hass,
        mode,
        **{
            ATTR_HVAC_MODES: [HVACMode.DRY, HVACMode.FAN_ONLY, HVACMode.OFF],
            ATTR_HVAC_ACTION: action,
        },
    )
    accessory = _accessory(hass, hk_driver)
    assert accessory.char_active.value == 1
    assert accessory.char_current_state.value == HC_IDLE


async def test_derives_hvac_action_when_integration_omits_it(
    hass: HomeAssistant, hk_driver: object
) -> None:
    set_climate(
        hass,
        HVACMode.COOL,
        **{
            ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF],
            ATTR_TEMPERATURE: 20,
            ATTR_CURRENT_TEMPERATURE: 23,
        },
    )
    accessory = _accessory(hass, hk_driver)
    assert accessory.char_current_state.value == HC_COOLING


async def test_humidity_is_exposed_as_a_linked_sensor(
    hass: HomeAssistant, hk_driver: object
) -> None:
    set_climate(
        hass,
        HVACMode.COOL,
        **{ATTR_CURRENT_HUMIDITY: 55},
    )
    accessory = _accessory(hass, hk_driver)
    humidity_service = accessory.get_service(SERV_HUMIDITY_SENSOR)

    assert humidity_service is not None
    assert accessory.char_current_humidity.value == 55
    assert humidity_service.is_primary_service is False


async def test_unsupported_target_is_restored(
    hass: HomeAssistant, hk_driver: object
) -> None:
    set_climate(
        hass,
        HVACMode.COOL,
        **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]},
    )
    accessory = _accessory(hass, hk_driver)
    calls = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE)

    accessory._set_chars({CHAR_TARGET_HEATER_COOLER_STATE: HC_TARGET_HEAT})
    await hass.async_block_till_done()

    assert not calls
    assert accessory.char_target_state.value == HC_TARGET_COOL


async def test_active_write_uses_ordered_service_calls(
    hass: HomeAssistant, hk_driver: object
) -> None:
    set_climate(
        hass,
        HVACMode.OFF,
        **{
            ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.HEAT, HVACMode.OFF],
            ATTR_TEMPERATURE: 22,
        },
    )
    accessory = _accessory(hass, hk_driver)
    hvac_calls = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE)
    temperature_calls = async_mock_service(
        hass, CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE
    )

    accessory._set_chars(
        {
            CHAR_ACTIVE: 1,
            CHAR_TARGET_HEATER_COOLER_STATE: HC_TARGET_HEAT,
            CHAR_HEATING_THRESHOLD_TEMPERATURE: 20,
        }
    )
    await hass.async_block_till_done()

    assert hvac_calls[-1].data["hvac_mode"] == HVACMode.HEAT
    assert temperature_calls[-1].data[ATTR_TEMPERATURE] == 20


async def test_off_write_stops_a_batched_temperature_change(
    hass: HomeAssistant, hk_driver: object
) -> None:
    set_climate(
        hass,
        HVACMode.COOL,
        **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]},
    )
    accessory = _accessory(hass, hk_driver)
    hvac_calls = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE)
    temperature_calls = async_mock_service(
        hass, CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE
    )

    accessory._set_chars({CHAR_ACTIVE: 0, CHAR_COOLING_THRESHOLD_TEMPERATURE: 25})
    await hass.async_block_till_done()

    assert hvac_calls[-1].data["hvac_mode"] == HVACMode.OFF
    assert not temperature_calls


async def test_invalid_raw_active_value_is_ignored(
    hass: HomeAssistant, hk_driver: object
) -> None:
    set_climate(hass, HVACMode.OFF, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    accessory = _accessory(hass, hk_driver)
    calls = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE)

    accessory._set_chars({CHAR_ACTIVE: float("nan")})
    await hass.async_block_till_done()

    assert not calls


async def test_reload_attributes_follow_core_shape_contract(
    hass: HomeAssistant, hk_driver: object
) -> None:
    set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    accessory = _accessory(hass, hk_driver)
    for attr in ("min_temp", "max_temp", "fan_modes", "swing_modes", "hvac_modes"):
        assert attr in accessory._reload_on_change_attrs


async def test_range_target_writes_both_temperatures(
    hass: HomeAssistant, hk_driver: object
) -> None:
    set_climate(
        hass,
        HVACMode.HEAT_COOL,
        **{
            ATTR_SUPPORTED_FEATURES: ClimateEntityFeature.TARGET_TEMPERATURE_RANGE,
            ATTR_HVAC_MODES: [HVACMode.HEAT_COOL, HVACMode.OFF],
            ATTR_TARGET_TEMP_HIGH: 26,
            ATTR_TARGET_TEMP_LOW: 20,
        },
    )
    accessory = _accessory(hass, hk_driver)
    calls = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE)

    accessory._set_chars({CHAR_COOLING_THRESHOLD_TEMPERATURE: 28})
    await hass.async_block_till_done()

    assert calls[-1].data[ATTR_TARGET_TEMP_HIGH] == 28
    assert calls[-1].data[ATTR_TARGET_TEMP_LOW] == 20


async def test_off_state_is_inactive(hass: HomeAssistant, hk_driver: object) -> None:
    set_climate(hass, HVACMode.OFF, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    accessory = _accessory(hass, hk_driver)
    assert accessory.char_current_state.value == HC_INACTIVE


async def test_fahrenheit_temperatures_round_trip_through_homekit(
    hass: HomeAssistant, hk_driver: object
) -> None:
    """Fahrenheit entities keep their HomeKit values in Celsius."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    set_climate(
        hass,
        HVACMode.HEAT,
        **{
            ATTR_HVAC_MODES: [HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF],
            ATTR_MIN_TEMP: 45,
            ATTR_MAX_TEMP: 95,
            ATTR_TEMPERATURE: 68,
            ATTR_CURRENT_TEMPERATURE: 65,
        },
    )
    accessory = _accessory(hass, hk_driver)
    calls = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE)

    assert accessory.char_heat.value == pytest.approx(20)
    assert accessory.char_current_temp.value == pytest.approx(18.3, abs=0.1)
    assert accessory.char_heat.properties["minValue"] == pytest.approx(7.3)
    assert accessory.char_heat.properties["maxValue"] == pytest.approx(35)

    accessory._set_chars({CHAR_HEATING_THRESHOLD_TEMPERATURE: 21})
    await hass.async_block_till_done()
    assert calls[-1].data[ATTR_TEMPERATURE] == pytest.approx(69.8, abs=0.1)


async def test_fahrenheit_default_temperature_bounds_stay_celsius(
    hass: HomeAssistant, hk_driver: object
) -> None:
    """Core defaults are already HomeKit Celsius values, not state temperatures."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    hass.states.async_set(
        ENTITY_ID,
        HVACMode.HEAT,
        {
            ATTR_SUPPORTED_FEATURES: ClimateEntityFeature.TARGET_TEMPERATURE,
            ATTR_HVAC_MODES: [HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF],
            ATTR_TEMPERATURE: 68,
        },
    )
    accessory = _accessory(hass, hk_driver)
    assert accessory.char_heat.properties["minValue"] == 7
    assert accessory.char_heat.properties["maxValue"] == 35


async def test_dual_capable_entity_uses_effective_mode_for_setpoint_shape(
    hass: HomeAssistant, hk_driver: object
) -> None:
    """Range keys do not force range writes while a single mode is active."""
    set_climate(
        hass,
        HVACMode.HEAT,
        **{
            ATTR_SUPPORTED_FEATURES: (
                ClimateEntityFeature.TARGET_TEMPERATURE
                | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
            ),
            ATTR_HVAC_MODES: [
                HVACMode.HEAT,
                HVACMode.COOL,
                HVACMode.HEAT_COOL,
                HVACMode.OFF,
            ],
            ATTR_TARGET_TEMP_HIGH: None,
            ATTR_TARGET_TEMP_LOW: None,
            ATTR_TEMPERATURE: 22,
        },
    )
    accessory = _accessory(hass, hk_driver)
    hvac_calls = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE)
    temperature_calls = async_mock_service(
        hass, CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE
    )

    accessory._set_chars({CHAR_HEATING_THRESHOLD_TEMPERATURE: 21})
    await hass.async_block_till_done()
    assert temperature_calls[-1].data[ATTR_TEMPERATURE] == 21
    assert ATTR_TARGET_TEMP_HIGH not in temperature_calls[-1].data

    accessory._set_chars(
        {
            CHAR_TARGET_HEATER_COOLER_STATE: HC_TARGET_COOL,
            CHAR_COOLING_THRESHOLD_TEMPERATURE: 26,
            CHAR_HEATING_THRESHOLD_TEMPERATURE: 16,
        }
    )
    await hass.async_block_till_done()
    assert hvac_calls[-1].data[ATTR_HVAC_MODE] == HVACMode.COOL
    assert temperature_calls[-1].data[ATTR_TEMPERATURE] == 26


async def test_single_cool_mode_ignores_heating_threshold_write(
    hass: HomeAssistant, hk_driver: object
) -> None:
    """The inactive threshold does not alter a single-setpoint cooler."""
    set_climate(
        hass,
        HVACMode.COOL,
        **{
            ATTR_HVAC_MODES: [HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF],
            ATTR_TEMPERATURE: 22,
        },
    )
    accessory = _accessory(hass, hk_driver)
    calls = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE)

    accessory._set_chars({CHAR_HEATING_THRESHOLD_TEMPERATURE: 18})
    await hass.async_block_till_done()
    assert not calls


@pytest.mark.parametrize("state_value", [STATE_UNAVAILABLE, STATE_UNKNOWN])
async def test_unavailable_and_unknown_are_inactive_without_losing_target(
    hass: HomeAssistant, hk_driver: object, state_value: str
) -> None:
    """Unavailable state must not replace the tile's last useful target mode."""
    attributes = {
        ATTR_SUPPORTED_FEATURES: ClimateEntityFeature.TARGET_TEMPERATURE,
        ATTR_HVAC_MODES: [HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF],
        ATTR_TEMPERATURE: 22,
    }
    set_climate(hass, HVACMode.COOL, **attributes)
    accessory = _accessory(hass, hk_driver)

    accessory.async_update_state(State(ENTITY_ID, state_value, attributes))
    assert accessory.char_active.value == 0
    assert accessory.char_current_state.value == HC_INACTIVE
    assert accessory.char_target_state.value == HC_TARGET_COOL


async def test_pending_mode_bridges_stale_entity_updates(
    hass: HomeAssistant, hk_driver: object
) -> None:
    """Accepted mode writes remain effective until a new mode is reported."""
    attributes = {
        ATTR_HVAC_MODES: [HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF],
        ATTR_TEMPERATURE: 20,
    }
    set_climate(hass, HVACMode.HEAT, **attributes)
    accessory = _accessory(hass, hk_driver)
    async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE)
    temperature_calls = async_mock_service(
        hass, CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE
    )

    accessory._set_chars({CHAR_TARGET_HEATER_COOLER_STATE: HC_TARGET_COOL})
    await hass.async_block_till_done()
    assert accessory._pending_mode == HVACMode.COOL

    accessory._set_chars({CHAR_COOLING_THRESHOLD_TEMPERATURE: 22})
    await hass.async_block_till_done()
    assert temperature_calls[-1].data[ATTR_TEMPERATURE] == 22

    accessory.async_update_state(State(ENTITY_ID, HVACMode.HEAT, attributes))
    assert accessory._pending_mode == HVACMode.COOL
    assert accessory.char_target_state.value == HC_TARGET_COOL
    assert accessory._last_known_mode == HVACMode.COOL

    accessory.async_update_state(State(ENTITY_ID, HVACMode.COOL, attributes))
    assert accessory._pending_mode is None


async def test_failed_mode_write_aborts_temperature_and_fan_writes(
    hass: HomeAssistant, hk_driver: object
) -> None:
    """A rejected HVAC mode prevents later writes from targeting the wrong mode."""
    set_climate(
        hass,
        HVACMode.OFF,
        **{
            ATTR_HVAC_MODES: [HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF],
            ATTR_FAN_MODES: ["Low", "High"],
            ATTR_FAN_MODE: "Low",
            ATTR_TEMPERATURE: 20,
        },
    )
    accessory = _accessory(hass, hk_driver)
    async_mock_service(
        hass,
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        raise_exception=HomeAssistantError("mode rejected"),
    )
    temperature_calls = async_mock_service(
        hass, CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE
    )
    fan_calls = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_FAN_MODE)

    accessory._set_chars(
        {
            CHAR_ACTIVE: 1,
            CHAR_COOLING_THRESHOLD_TEMPERATURE: 22,
            CHAR_ROTATION_SPEED: 100,
        }
    )
    await hass.async_block_till_done()
    assert not temperature_calls
    assert not fan_calls


async def test_write_batches_are_serialized(
    hass: HomeAssistant, hk_driver: object
) -> None:
    """The next HomeKit batch waits for the previous mode and temperature writes."""
    set_climate(
        hass,
        HVACMode.OFF,
        **{
            ATTR_HVAC_MODES: [HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF],
            ATTR_TEMPERATURE: 20,
        },
    )
    accessory = _accessory(hass, hk_driver)
    gate = asyncio.Event()
    order: list[str] = []

    async def slow_hvac(call: ServiceCall) -> None:
        order.append(f"hvac:{call.data[ATTR_HVAC_MODE]}")
        if len(order) == 1:
            await gate.wait()

    async def record_temperature(_call: ServiceCall) -> None:
        order.append("temperature")

    hass.services.async_register(CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE, slow_hvac)
    hass.services.async_register(
        CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE, record_temperature
    )

    accessory._set_chars(
        {
            CHAR_TARGET_HEATER_COOLER_STATE: HC_TARGET_COOL,
            CHAR_COOLING_THRESHOLD_TEMPERATURE: 22,
        }
    )
    accessory._set_chars({CHAR_TARGET_HEATER_COOLER_STATE: HC_TARGET_HEAT})
    await asyncio.sleep(0)
    assert order == ["hvac:cool"]

    gate.set()
    await hass.async_block_till_done()
    assert order == ["hvac:cool", "temperature", "hvac:heat"]


async def test_off_with_target_remembers_the_next_power_on_mode(
    hass: HomeAssistant, hk_driver: object
) -> None:
    """An off batch commits its selected target for the following Active write."""
    set_climate(
        hass,
        HVACMode.COOL,
        **{ATTR_HVAC_MODES: [HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF]},
    )
    accessory = _accessory(hass, hk_driver)
    calls = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE)

    accessory._set_chars(
        {CHAR_ACTIVE: 0, CHAR_TARGET_HEATER_COOLER_STATE: HC_TARGET_HEAT}
    )
    await hass.async_block_till_done()
    assert calls[-1].data[ATTR_HVAC_MODE] == HVACMode.OFF
    assert accessory._last_known_mode == HVACMode.HEAT

    hass.states.async_set(
        ENTITY_ID,
        HVACMode.OFF,
        {ATTR_HVAC_MODES: [HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF]},
    )
    await hass.async_block_till_done()
    accessory._set_chars({CHAR_ACTIVE: 1})
    await hass.async_block_till_done()
    assert calls[-1].data[ATTR_HVAC_MODE] == HVACMode.HEAT


async def test_state_reported_during_write_wins_over_pending_mode(
    hass: HomeAssistant, hk_driver: object
) -> None:
    """A synchronous entity report is newer than the requested target."""
    attributes = {
        ATTR_SUPPORTED_FEATURES: ClimateEntityFeature.TARGET_TEMPERATURE,
        ATTR_HVAC_MODES: [
            HVACMode.HEAT,
            HVACMode.COOL,
            HVACMode.HEAT_COOL,
            HVACMode.OFF,
        ],
    }
    set_climate(hass, HVACMode.HEAT, **attributes)
    accessory = _accessory(hass, hk_driver)
    accessory.run()
    await hass.async_block_till_done()

    async def normalize_mode(_call: ServiceCall) -> None:
        reported = State(ENTITY_ID, HVACMode.HEAT_COOL, attributes)
        hass.states.async_set(ENTITY_ID, HVACMode.HEAT_COOL, attributes)
        accessory.async_update_state(reported)

    hass.services.async_register(CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE, normalize_mode)
    accessory._set_chars({CHAR_TARGET_HEATER_COOLER_STATE: HC_TARGET_COOL})
    await hass.async_block_till_done()

    assert accessory._pending_mode is None
    assert accessory._last_known_mode == HVACMode.HEAT_COOL


async def test_entity_without_off_mode_stays_active_and_applies_target(
    hass: HomeAssistant, hk_driver: object
) -> None:
    """A rejected Active-off write must not suppress a bundled valid target."""
    set_climate(
        hass,
        HVACMode.COOL,
        **{
            ATTR_HVAC_MODES: [HVACMode.HEAT, HVACMode.COOL],
            ATTR_TEMPERATURE: 22,
        },
    )
    accessory = _accessory(hass, hk_driver)
    hvac_calls = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE)
    temperature_calls = async_mock_service(
        hass, CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE
    )

    accessory._set_chars(
        {
            CHAR_ACTIVE: 0,
            CHAR_TARGET_HEATER_COOLER_STATE: HC_TARGET_HEAT,
            CHAR_HEATING_THRESHOLD_TEMPERATURE: 20,
        }
    )
    await hass.async_block_till_done()

    assert accessory.char_active.value == 1
    assert hvac_calls[-1].data[ATTR_HVAC_MODE] == HVACMode.HEAT
    assert temperature_calls[-1].data[ATTR_TEMPERATURE] == 20


async def test_absent_swing_mode_keeps_the_last_reported_value(
    hass: HomeAssistant, hk_driver: object
) -> None:
    """An entity that drops the attribute must not read as swing off.

    Reporting off would assert a state the entity never gave us, and the Home
    app would show the toggle flipping on its own.
    """
    swing = {
        ATTR_SUPPORTED_FEATURES: (
            ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.SWING_MODE
        ),
        ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF],
        ATTR_SWING_MODES: ["off", "on"],
    }
    set_climate(hass, HVACMode.COOL, **swing, **{ATTR_SWING_MODE: "on"})
    accessory = _accessory(hass, hk_driver)
    accessory.async_update_state(hass.states.get(ENTITY_ID))
    assert accessory.char_swing is not None
    assert accessory.char_swing.value == 1

    set_climate(hass, HVACMode.COOL, **swing)
    accessory.async_update_state(hass.states.get(ENTITY_ID))
    assert accessory.char_swing.value == 1

    set_climate(hass, HVACMode.COOL, **swing, **{ATTR_SWING_MODE: "off"})
    accessory.async_update_state(hass.states.get(ENTITY_ID))
    assert accessory.char_swing.value == 0


FAN_ENTITY_ID = "fan.living"


def _set_fan(hass: HomeAssistant, percentage: int, **extra: object) -> None:
    """Register the linked fan entity, independent of the climate entity."""
    attributes: dict[str, object] = {
        ATTR_PERCENTAGE: percentage,
        ATTR_PERCENTAGE_STEP: 100 / 3,
    }
    attributes.update(extra)
    hass.states.async_set(FAN_ENTITY_ID, "on" if percentage else "off", attributes)


async def test_fan_entity_override_exposes_rotation_speed_without_climate_fan_modes(
    hass: HomeAssistant, hk_driver: object
) -> None:
    """A configured fan entity drives RotationSpeed even without climate fan_modes."""
    set_climate(
        hass,
        HVACMode.COOL,
        **{
            ATTR_SUPPORTED_FEATURES: 0,
            ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF],
            ATTR_FAN_MODES: None,
        },
    )
    _set_fan(hass, 66)
    accessory = _accessory(hass, hk_driver, {CONF_FAN_ENTITY_ID: FAN_ENTITY_ID})

    assert accessory.fan_entity_id == FAN_ENTITY_ID
    assert accessory.ordered_fan_speeds == []
    assert accessory.char_speed is not None
    assert accessory.char_speed.value == 66
    assert accessory.char_speed.properties["minStep"] == pytest.approx(100 / 3)


async def test_fan_entity_override_writes_target_domain_and_percentage(
    hass: HomeAssistant, hk_driver: object
) -> None:
    """RotationSpeed writes call fan.set_percentage on the linked entity."""
    set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    _set_fan(hass, 0)
    accessory = _accessory(hass, hk_driver, {CONF_FAN_ENTITY_ID: FAN_ENTITY_ID})
    fan_calls = async_mock_service(hass, FAN_DOMAIN, SERVICE_SET_PERCENTAGE)
    climate_fan_calls = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_FAN_MODE)

    accessory._set_chars({CHAR_ROTATION_SPEED: 50})
    await hass.async_block_till_done()

    assert not climate_fan_calls
    assert fan_calls[-1].data[ATTR_ENTITY_ID] == FAN_ENTITY_ID
    # Snapped to the fan's own 33.3%-wide steps rather than written raw.
    assert fan_calls[-1].data[ATTR_PERCENTAGE] == pytest.approx(100 / 3 * 2, abs=0.1)


async def test_fan_entity_override_zero_speed_turns_the_fan_off(
    hass: HomeAssistant, hk_driver: object
) -> None:
    """A slider write to zero calls fan.turn_off, not set_percentage(0)."""
    set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    _set_fan(hass, 100)
    accessory = _accessory(hass, hk_driver, {CONF_FAN_ENTITY_ID: FAN_ENTITY_ID})
    turn_off_calls = async_mock_service(hass, FAN_DOMAIN, SERVICE_TURN_OFF)

    accessory._set_chars({CHAR_ROTATION_SPEED: 0})
    await hass.async_block_till_done()

    assert turn_off_calls[-1].data[ATTR_ENTITY_ID] == FAN_ENTITY_ID


async def test_fan_entity_override_ignores_climate_fan_mode_changes(
    hass: HomeAssistant, hk_driver: object
) -> None:
    """Once a fan entity is linked, climate fan_mode updates no longer apply."""
    set_climate(
        hass,
        HVACMode.COOL,
        **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF], ATTR_FAN_MODE: "High"},
    )
    _set_fan(hass, 40)
    accessory = _accessory(hass, hk_driver, {CONF_FAN_ENTITY_ID: FAN_ENTITY_ID})
    assert accessory.char_speed.value == 40

    set_climate(
        hass,
        HVACMode.COOL,
        **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF], ATTR_FAN_MODE: "Low"},
    )
    accessory.async_update_state(hass.states.get(ENTITY_ID))
    assert accessory.char_speed.value == 40

    _set_fan(hass, 80)
    accessory.async_update_state(hass.states.get(ENTITY_ID))
    assert accessory.char_speed.value == 80


async def test_fan_entity_state_change_updates_rotation_speed_live(
    hass: HomeAssistant, hk_driver: object
) -> None:
    """The fan entity's own state changes refresh RotationSpeed on their own."""
    set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    _set_fan(hass, 33)
    accessory = _accessory(hass, hk_driver, {CONF_FAN_ENTITY_ID: FAN_ENTITY_ID})
    accessory.run()
    await hass.async_block_till_done()

    _set_fan(hass, 90)
    await hass.async_block_till_done()

    assert accessory.char_speed.value == 90
