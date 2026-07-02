"""Tests for the runtime patcher: routing and hardening helpers."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.components.climate import (
    ATTR_FAN_MODES,
    ATTR_HVAC_MODES,
    ATTR_SWING_MODES,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.homekit import accessories as homekit_accessories
from homeassistant.const import ATTR_SUPPORTED_FEATURES
from homeassistant.core import HomeAssistant, State

from custom_components.homekit_heatercooler.patcher import (
    EXPECTED_GET_ACCESSORY_PARAMS,
    _get_accessory_params,
    _should_patch_entity,
    apply_patch,
    remove_patch,
    supports_heatercooler,
)
from tests.common import ENTITY_ID, set_climate


def _state(**attributes: object) -> State:
    return State("climate.test", "cool", attributes)


def test_supports_heatercooler_with_fan_modes() -> None:
    state = _state(
        **{
            ATTR_SUPPORTED_FEATURES: ClimateEntityFeature.FAN_MODE,
            ATTR_FAN_MODES: ["low", "high"],
        }
    )
    assert supports_heatercooler(state) is True


def test_supports_heatercooler_with_swing_modes() -> None:
    state = _state(
        **{
            ATTR_SUPPORTED_FEATURES: ClimateEntityFeature.SWING_MODE,
            ATTR_SWING_MODES: ["on", "off"],
        }
    )
    assert supports_heatercooler(state) is True


def test_supports_heatercooler_feature_without_modes() -> None:
    state = _state(**{ATTR_SUPPORTED_FEATURES: ClimateEntityFeature.FAN_MODE})
    assert supports_heatercooler(state) is False


def test_supports_heatercooler_modes_without_feature() -> None:
    state = _state(**{ATTR_SUPPORTED_FEATURES: 0, ATTR_FAN_MODES: ["low"]})
    assert supports_heatercooler(state) is False


def test_should_patch_entity() -> None:
    assert _should_patch_entity("climate.a", {"climate.a"}, set()) is True
    assert _should_patch_entity("climate.a", {"climate.a"}, {"climate.a"}) is False
    assert _should_patch_entity("climate.a", set(), set()) is False
    assert _should_patch_entity("climate.b", {"climate.a"}, set()) is False


def test_get_accessory_params_matches_expected() -> None:
    def get_accessory(hass, driver, state, aid, config):
        return None

    params = _get_accessory_params(get_accessory)
    assert params[: len(EXPECTED_GET_ACCESSORY_PARAMS)] == EXPECTED_GET_ACCESSORY_PARAMS


def test_get_accessory_params_uninspectable_returns_empty() -> None:
    assert _get_accessory_params(object()) == ()


def test_real_get_accessory_matches_expected_signature() -> None:
    """Canary: fail loudly if Home Assistant changes the get_accessory signature."""
    assert _get_accessory_params(homekit_accessories.get_accessory) == EXPECTED_GET_ACCESSORY_PARAMS


async def test_patch_routes_included_climate_and_restores(hass: HomeAssistant, hk_driver: object) -> None:
    set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    original = homekit_accessories.get_accessory
    apply_patch(hass, {ENTITY_ID}, set())
    try:
        assert homekit_accessories.get_accessory is not original
        state = hass.states.get(ENTITY_ID)
        accessory = homekit_accessories.get_accessory(hass, hk_driver, state, 2, {})
        assert type(accessory).__name__ == "HeaterCooler"
    finally:
        remove_patch(hass)
    assert homekit_accessories.get_accessory is original


async def test_patch_falls_back_to_default_on_error(hass: HomeAssistant, hk_driver: object) -> None:
    set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    apply_patch(hass, {ENTITY_ID}, set())

    def _raise(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    try:
        state = hass.states.get(ENTITY_ID)
        with patch.dict(homekit_accessories.TYPES, {"HeaterCooler": _raise}):
            accessory = homekit_accessories.get_accessory(hass, hk_driver, state, 2, {})
        assert type(accessory).__name__ == "Thermostat"
    finally:
        remove_patch(hass)
