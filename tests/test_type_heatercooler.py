"""Tests for the HeaterCooler accessory and its pure helpers."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.components.climate import (
    ATTR_FAN_MODE,
    ATTR_HVAC_MODES,
    SERVICE_SET_FAN_MODE,
    HVACMode,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant

from custom_components.homekit_heatercooler.type_heatercooler import (
    HC_INACTIVE,
    HeaterCooler,
    _as_float,
    build_target_state_map,
    target_state_valid_values,
)
from tests.common import set_climate as _set_climate


def test_as_float() -> None:
    assert _as_float(3) == 3.0
    assert _as_float(3.5) == 3.5
    assert _as_float(True) == 1.0
    assert _as_float(None) is None
    assert _as_float("nope") is None


def test_target_state_map_omits_auto_when_unsupported() -> None:
    valid = target_state_valid_values(build_target_state_map(False, False))
    assert set(valid) == {"Heat", "Cool"}
    assert "Auto" not in valid


@pytest.mark.parametrize(
    ("supports_auto", "supports_heat_cool"),
    [(True, False), (False, True), (True, True)],
)
def test_target_state_map_offers_auto_when_supported(supports_auto: bool, supports_heat_cool: bool) -> None:
    valid = target_state_valid_values(build_target_state_map(supports_auto, supports_heat_cool))
    assert "Auto" in valid


async def test_accessory_hides_auto_for_heat_cool_only_entity(hass: HomeAssistant, hk_driver: object) -> None:
    """A heat/cool-only entity must not expose Auto on the HeaterCooler (bug #4)."""
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
    """Starting from off must not seed the last mode to OFF (bug #5)."""
    _set_climate(hass, HVACMode.OFF, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.HEAT, HVACMode.OFF]})
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    assert acc._last_known_mode != HVACMode.OFF


async def test_current_state_inactive_when_off(hass: HomeAssistant, hk_driver: object) -> None:
    """An off entity without hvac_action maps to Inactive, not Idle (bug #6)."""
    _set_climate(hass, HVACMode.OFF, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    acc = HeaterCooler(hass, hk_driver, "Test", "climate.test", 2, {})
    assert acc.char_current_state.value == HC_INACTIVE


async def test_lowest_fan_step_reaches_first_mode(hass: HomeAssistant, hk_driver: object) -> None:
    """The lowest slider step reaches the first ordered fan mode (bug #3)."""
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
