"""Tests for the HeaterCooler accessory and its pure helpers."""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_HVAC_MODE,
    ATTR_HVAC_MODES,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_SWING_MODE,
    ATTR_SWING_MODES,
    ATTR_TARGET_TEMP_STEP,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_SWING_MODE,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_SUPPORTED_FEATURES
from homeassistant.core import HomeAssistant
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from custom_components.homekit_heatercooler.climate_util import (
    HC_INACTIVE,
    HC_TARGET_COOL,
    as_float,
    build_target_state_map,
    target_state_valid_values,
)
from custom_components.homekit_heatercooler.const import CONF_FAN_LANE, FAN_LANE_AUTO, FAN_LANE_MANUAL
from custom_components.homekit_heatercooler.type_heatercooler import (
    CHAR_ACTIVE,
    CHAR_ROTATION_SPEED,
    CHAR_SWING_MODE,
    CHAR_TARGET_HEATER_COOLER_STATE,
    PROP_MIN_STEP,
    HeaterCooler,
)
from tests.common import set_climate as _set_climate

SEVEN_FAN_MODES = ["Auto", "Low", "Mid", "High", "Low/Auto", "Mid/Auto", "High/Auto"]


def _characteristic_names(acc: HeaterCooler) -> set[str]:
    """Return the exposed HomeKit characteristic display names."""
    return {char.display_name for service in acc.services for char in service.characteristics}


def test_as_float() -> None:
    assert as_float(3) == 3.0
    assert as_float(3.5) == 3.5
    assert as_float(True) == 1.0
    assert as_float(None) is None
    assert as_float("nope") is None
    # Non-finite values a HomeKit client can send must not leak into arithmetic.
    assert as_float(float("nan")) is None
    assert as_float(float("inf")) is None
    assert as_float(float("-inf")) is None


def test_target_state_map_omits_auto_when_unsupported() -> None:
    valid = target_state_valid_values(build_target_state_map(False, False, True, True))
    assert set(valid) == {"Heat", "Cool"}
    assert "Auto" not in valid


def test_target_state_map_honours_heat_cool_capability() -> None:
    cool_only = target_state_valid_values(build_target_state_map(False, False, False, True))
    assert set(cool_only) == {"Cool"}
    heat_only = target_state_valid_values(build_target_state_map(False, False, True, False))
    assert set(heat_only) == {"Heat"}
    both = target_state_valid_values(build_target_state_map(False, False, True, True))
    assert set(both) == {"Heat", "Cool"}


@pytest.mark.parametrize(
    ("supports_auto", "supports_heat_cool"),
    [(True, False), (False, True), (True, True)],
)
def test_target_state_map_offers_auto_when_supported(supports_auto: bool, supports_heat_cool: bool) -> None:
    valid = target_state_valid_values(build_target_state_map(supports_auto, supports_heat_cool, True, True))
    assert "Auto" in valid


async def test_accessory_hides_auto_for_heat_cool_only_entity(hass: HomeAssistant, hk_driver: object) -> None:
    """A heat/cool-only entity must not expose Auto on the HeaterCooler."""
    _set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.HEAT, HVACMode.OFF]})
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    valid_values = acc.char_target_state.properties["ValidValues"]
    assert "Auto" not in valid_values


async def test_accessory_offers_auto_for_heat_cool_entity(hass: HomeAssistant, hk_driver: object) -> None:
    _set_climate(
        hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.HEAT, HVACMode.HEAT_COOL, HVACMode.OFF]}
    )
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    assert "Auto" in acc.char_target_state.properties["ValidValues"]


async def test_last_known_mode_is_not_off_when_starting_off(hass: HomeAssistant, hk_driver: object) -> None:
    """Starting from off must not seed the last mode to OFF."""
    _set_climate(hass, HVACMode.OFF, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.HEAT, HVACMode.OFF]})
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    assert acc._last_known_mode != HVACMode.OFF


async def test_power_on_uses_supported_mode_for_heat_only_entity(hass: HomeAssistant, hk_driver: object) -> None:
    """A heat-only entity starting off must power on with HEAT, not the COOL it lacks."""
    _set_climate(hass, HVACMode.OFF, **{ATTR_HVAC_MODES: [HVACMode.HEAT, HVACMode.OFF]})
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    assert acc._last_known_mode == HVACMode.HEAT
    with patch.object(acc, "async_call_service") as mock_call:
        acc._set_chars({CHAR_ACTIVE: 1})
    mock_call.assert_called_once_with(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: "climate.test", ATTR_HVAC_MODE: HVACMode.HEAT},
    )


async def test_cool_only_entity_omits_heat_target(hass: HomeAssistant, hk_driver: object) -> None:
    """A cool-only entity must not advertise a Heat target it cannot honour."""
    _set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    valid_values = acc.char_target_state.properties["ValidValues"]
    assert "Cool" in valid_values
    assert "Heat" not in valid_values


async def test_heat_only_entity_omits_cool_target(hass: HomeAssistant, hk_driver: object) -> None:
    """A heat-only entity must not advertise a Cool target it cannot honour."""
    _set_climate(hass, HVACMode.HEAT, **{ATTR_HVAC_MODES: [HVACMode.HEAT, HVACMode.OFF]})
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    valid_values = acc.char_target_state.properties["ValidValues"]
    assert "Heat" in valid_values
    assert "Cool" not in valid_values


async def test_heat_cool_entity_offers_both_targets(hass: HomeAssistant, hk_driver: object) -> None:
    """An entity supporting both directions advertises both Heat and Cool targets."""
    _set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.HEAT, HVACMode.OFF]})
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    valid_values = acc.char_target_state.properties["ValidValues"]
    assert "Heat" in valid_values
    assert "Cool" in valid_values


async def test_capability_less_entity_falls_back_to_cool_target(hass: HomeAssistant, hk_driver: object) -> None:
    """A fan/dry-only entity still constructs, falling back to a single Cool target."""
    _set_climate(hass, HVACMode.FAN_ONLY, **{ATTR_HVAC_MODES: [HVACMode.FAN_ONLY, HVACMode.DRY, HVACMode.OFF]})
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    assert set(acc.char_target_state.properties["ValidValues"]) == {"Cool"}


async def test_capability_less_target_write_is_noop(hass: HomeAssistant, hk_driver: object) -> None:
    """Selecting the fallback Cool target on a fan/dry-only entity issues no service call."""
    _set_climate(hass, HVACMode.FAN_ONLY, **{ATTR_HVAC_MODES: [HVACMode.FAN_ONLY, HVACMode.DRY, HVACMode.OFF]})
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    with patch.object(acc, "async_call_service") as mock_call:
        acc._set_chars({CHAR_TARGET_HEATER_COOLER_STATE: HC_TARGET_COOL})
    assert not mock_call.called
    assert acc._last_known_mode == HVACMode.FAN_ONLY


async def test_active_and_unsupported_target_powers_on_supported_mode(hass: HomeAssistant, hk_driver: object) -> None:
    """A combined Active=1 and unsupported target write powers on a supported mode."""
    _set_climate(hass, HVACMode.OFF, **{ATTR_HVAC_MODES: [HVACMode.FAN_ONLY, HVACMode.OFF]})
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    assert acc._last_known_mode == HVACMode.FAN_ONLY
    with patch.object(acc, "async_call_service") as mock_call:
        acc._set_chars({CHAR_ACTIVE: 1, CHAR_TARGET_HEATER_COOLER_STATE: HC_TARGET_COOL})
    mock_call.assert_called_once_with(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: "climate.test", ATTR_HVAC_MODE: HVACMode.FAN_ONLY},
    )
    assert acc._last_known_mode == HVACMode.FAN_ONLY


async def test_initial_target_matches_power_on_mode_when_off(hass: HomeAssistant, hk_driver: object) -> None:
    """An entity starting off shows the target mode it will power on with."""
    _set_climate(hass, HVACMode.OFF, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.HEAT, HVACMode.OFF]})
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    assert acc._last_known_mode == HVACMode.COOL
    assert acc.char_target_state.value == HC_TARGET_COOL


async def test_off_state_preserves_last_target_mode(hass: HomeAssistant, hk_driver: object) -> None:
    """Turning off must not reset the HomeKit target mode to Auto."""
    modes = [HVACMode.COOL, HVACMode.HEAT, HVACMode.HEAT_COOL, HVACMode.OFF]
    _set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: modes})
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    assert acc.char_target_state.value == HC_TARGET_COOL

    _set_climate(hass, HVACMode.OFF, **{ATTR_HVAC_MODES: modes})
    state = hass.states.get("climate.test")
    assert state
    acc.async_update_state(state)
    assert acc.char_target_state.value == HC_TARGET_COOL


async def test_reload_on_shape_change_attrs(hass: HomeAssistant, hk_driver: object) -> None:
    """A live modes or min/max change must reshape the accessory via the base reload path."""
    _set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    for attr in (ATTR_HVAC_MODES, ATTR_FAN_MODES, ATTR_SWING_MODES, ATTR_MIN_TEMP, ATTR_MAX_TEMP):
        assert attr in acc._reload_on_change_attrs


async def test_current_state_inactive_when_off(hass: HomeAssistant, hk_driver: object) -> None:
    """An off entity without hvac_action maps to Inactive, not Idle."""
    _set_climate(hass, HVACMode.OFF, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    assert acc.char_current_state.value == HC_INACTIVE


async def test_lowest_fan_step_reaches_first_mode(hass: HomeAssistant, hk_driver: object) -> None:
    """The lowest slider step reaches the first ordered fan mode."""
    _set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    lowest_step = 100 / len(acc.ordered_fan_speeds)
    with patch.object(acc, "async_call_service") as mock_call:
        acc._set_fan_speed(lowest_step)
    mock_call.assert_called_once_with(
        CLIMATE_DOMAIN,
        SERVICE_SET_FAN_MODE,
        {ATTR_ENTITY_ID: "climate.test", ATTR_FAN_MODE: "Auto"},
    )


async def test_fan_lane_auto_uses_auto_trio(hass: HomeAssistant, hk_driver: object) -> None:
    """The auto lane maps the slider to the three /Auto fan modes."""
    _set_climate(
        hass,
        HVACMode.COOL,
        **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF], ATTR_FAN_MODES: SEVEN_FAN_MODES},
    )
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {CONF_FAN_LANE: FAN_LANE_AUTO})
    assert acc.ordered_fan_speeds == ["low/auto", "mid/auto", "high/auto"]


async def test_fan_lane_manual_uses_manual_trio(hass: HomeAssistant, hk_driver: object) -> None:
    """The manual lane maps the slider to Low/Mid/High."""
    _set_climate(
        hass,
        HVACMode.COOL,
        **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF], ATTR_FAN_MODES: SEVEN_FAN_MODES},
    )
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {CONF_FAN_LANE: FAN_LANE_MANUAL})
    assert acc.ordered_fan_speeds == ["low", "mid", "high"]


async def test_non_numeric_temperature_attrs_are_ignored(hass: HomeAssistant, hk_driver: object) -> None:
    """A malformed temperature attribute is ignored instead of raising."""
    _set_climate(
        hass,
        HVACMode.COOL,
        **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF], ATTR_CURRENT_TEMPERATURE: "unknown"},
    )
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    assert acc.char_current_temp.value == 21.0

    _set_climate(
        hass,
        HVACMode.COOL,
        **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF], ATTR_CURRENT_TEMPERATURE: 23},
    )
    state = hass.states.get("climate.test")
    assert state
    acc.async_update_state(state)
    assert acc.char_current_temp.value == 23.0


async def test_swing_on_fallback_skips_off_mode(hass: HomeAssistant, hk_driver: object) -> None:
    """Enabling swing on a level-named device picks a non-off mode, not swing_modes[0]."""
    _set_climate(
        hass,
        HVACMode.COOL,
        **{
            ATTR_SUPPORTED_FEATURES: ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.SWING_MODE,
            ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF],
            ATTR_SWING_MODES: ["off", "low", "high"],
            ATTR_SWING_MODE: "off",
        },
    )
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    assert acc.swing_on_mode == "low"
    with patch.object(acc, "async_call_service") as mock_call:
        acc._set_swing_mode(1)
    mock_call.assert_called_once_with(
        CLIMATE_DOMAIN,
        SERVICE_SET_SWING_MODE,
        {ATTR_ENTITY_ID: "climate.test", ATTR_SWING_MODE: "low"},
    )


async def test_swing_off_without_off_mode_is_noop(hass: HomeAssistant, hk_driver: object) -> None:
    """Turning swing off without an off-like mode issues no service call."""
    _set_climate(
        hass,
        HVACMode.COOL,
        **{
            ATTR_SUPPORTED_FEATURES: ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.SWING_MODE,
            ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF],
            ATTR_SWING_MODES: ["vertical", "horizontal"],
            ATTR_SWING_MODE: "horizontal",
        },
    )
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    with patch.object(acc, "async_call_service") as mock_call:
        acc._set_swing_mode(0)
    assert not mock_call.called


async def test_fan_and_swing_chars_require_modes(hass: HomeAssistant, hk_driver: object) -> None:
    """Feature flags without mode lists must not expose inert controls."""
    _set_climate(
        hass,
        HVACMode.COOL,
        **{
            ATTR_SUPPORTED_FEATURES: ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.SWING_MODE,
            ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF],
            ATTR_FAN_MODES: [],
            ATTR_SWING_MODES: [],
        },
    )
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    names = _characteristic_names(acc)
    assert CHAR_ROTATION_SPEED not in names
    assert CHAR_SWING_MODE not in names
    assert acc.char_speed is None
    assert acc.char_swing is None


@pytest.mark.parametrize(
    "hvac_modes",
    [
        [HVACMode.COOL, HVACMode.OFF],
        [HVACMode.COOL, HVACMode.HEAT, HVACMode.OFF],
    ],
)
async def test_target_state_restricted_values_do_not_log_error(
    hass: HomeAssistant,
    hk_driver: object,
    caplog: pytest.LogCaptureFixture,
    hvac_modes: list[HVACMode],
) -> None:
    """Restricting target values must not log a pyhap validation error at init."""
    _set_climate(hass, hvac_modes[0], **{ATTR_HVAC_MODES: hvac_modes})
    caplog.clear()
    caplog.set_level(logging.ERROR)
    HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


async def test_auto_state_forces_auto_even_when_unlisted(hass: HomeAssistant, hk_driver: object) -> None:
    """An entity currently in auto exposes Auto even if hvac_modes omits it."""
    _set_climate(hass, HVACMode.AUTO, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    assert "Auto" in acc.char_target_state.properties["ValidValues"]


async def test_fan_speed_reflects_entity_fan_mode(hass: HomeAssistant, hk_driver: object) -> None:
    """The rotation-speed slider mirrors the entity's reported fan mode."""
    _set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})

    # ordered_fan_speeds falls back to ["auto", "low", "high"]; "Low" is the
    # middle step (2 of 3), which is two thirds of the slider.
    _set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF], ATTR_FAN_MODE: "Low"})
    state = hass.states.get("climate.test")
    assert state
    acc.async_update_state(state)

    assert acc.char_speed is not None
    assert acc.char_speed.value == pytest.approx(100 * 2 / 3)


async def test_swing_write_noop_when_already_in_mode(hass: HomeAssistant, hk_driver: object) -> None:
    """Writing a swing value that matches the current mode issues no service call."""
    _set_climate(
        hass,
        HVACMode.COOL,
        **{
            ATTR_SUPPORTED_FEATURES: ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.SWING_MODE,
            ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF],
            ATTR_SWING_MODES: ["off", "on"],
            ATTR_SWING_MODE: "on",
        },
    )
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    with patch.object(acc, "async_call_service") as mock_call:
        acc._set_swing_mode(1)
    assert not mock_call.called


async def test_fahrenheit_scales_temperature_step(hass: HomeAssistant, hk_driver: object) -> None:
    """Fahrenheit units scale the threshold step into Celsius degrees."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    _set_climate(
        hass,
        HVACMode.COOL,
        **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF], ATTR_TARGET_TEMP_STEP: 1},
    )
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    assert acc.char_cool.properties[PROP_MIN_STEP] == pytest.approx(5.0 / 9.0)


async def test_target_temp_step_non_numeric_falls_back_to_one(hass: HomeAssistant, hk_driver: object) -> None:
    """A non-numeric target_temp_step must not crash init; the step falls back to 1."""
    _set_climate(
        hass,
        HVACMode.COOL,
        **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF], ATTR_TARGET_TEMP_STEP: "high"},
    )
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    assert acc.char_cool.properties[PROP_MIN_STEP] == 1.0
