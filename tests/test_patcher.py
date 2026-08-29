"""Tests for the runtime patcher: routing and hardening helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import logging
from unittest.mock import patch

import pytest

from custom_components.homekit_heatercooler.const import (
    CONF_FAN_ENTITY_ID,
    DATA_PATCH_STATE,
    DOMAIN,
    FAN_LANE_MANUAL,
    TYPE_HEATER_COOLER,
)
from custom_components.homekit_heatercooler.patcher import (
    EXPECTED_GET_ACCESSORY_PARAMS,
    _get_accessory_params,
    _should_patch_entity,
    apply_patch,
    native_heatercooler_available,
    remove_patch,
    supports_heatercooler,
)
from homeassistant.components import homekit as homekit_module
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
from tests.common import ENTITY_ID, set_climate

SEVEN_FAN_MODES = ["Auto", "Low", "Mid", "High", "Low/Auto", "Mid/Auto", "High/Auto"]
# Cores before 2026.8 have no CLIMATE_TYPES to import this from.
TYPE_THERMOSTAT = "thermostat"


def _state(**attributes: object) -> State:
    return State("climate.test", "cool", attributes)


@contextmanager
def core_without_native() -> Iterator[None]:
    """Present a core from before 2026.8, which has no HeaterCooler of its own."""
    with (
        patch.object(
            homekit_accessories,
            "CLIMATE_TYPES",
            {TYPE_THERMOSTAT: "Thermostat"},
            create=True,
        ),
        patch.dict(homekit_accessories.TYPES),
    ):
        yield


class _CoreHeaterCooler:
    """Stand-in for the HeaterCooler a 2026.8 core registers for itself."""


@contextmanager
def core_with_native() -> Iterator[None]:
    """Present a 2026.8 core, which registers its own HeaterCooler."""
    with (
        patch.object(
            homekit_accessories,
            "CLIMATE_TYPES",
            {TYPE_HEATER_COOLER: "HeaterCooler", TYPE_THERMOSTAT: "Thermostat"},
            create=True,
        ),
        patch.dict(homekit_accessories.TYPES, {"HeaterCooler": _CoreHeaterCooler}),
    ):
        yield


CORE_SHAPES = {"legacy": core_without_native, "native": core_with_native}


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


@pytest.mark.parametrize("bad_features", [None, "abc", [1, 2], float("nan")])
def test_supports_heatercooler_non_numeric_features_is_false(
    bad_features: object,
) -> None:
    """A malformed supported_features returns False, never raises."""
    state = _state(
        **{ATTR_SUPPORTED_FEATURES: bad_features, ATTR_FAN_MODES: ["low", "high"]}
    )
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
    assert (
        _get_accessory_params(homekit_accessories.get_accessory)
        == EXPECTED_GET_ACCESSORY_PARAMS
    )


async def test_patch_routes_included_climate_and_restores(
    hass: HomeAssistant, hk_driver: object
) -> None:
    set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    original = homekit_accessories.get_accessory
    original_module = homekit_module.get_accessory
    apply_patch(hass, {ENTITY_ID}, set())
    try:
        # Core resolves get_accessory via both the accessories module and the
        # homekit package, so both refs must point at the single wrapper.
        assert homekit_accessories.get_accessory is not original
        assert homekit_module.get_accessory is not original_module
        assert homekit_accessories.get_accessory is homekit_module.get_accessory
        state = hass.states.get(ENTITY_ID)
        accessory = homekit_accessories.get_accessory(hass, hk_driver, state, 2, {})
        assert type(accessory).__name__ == "HeaterCooler"
    finally:
        remove_patch(hass)
    # Removal must restore BOTH original refs, not just the accessories one.
    assert homekit_accessories.get_accessory is original
    assert homekit_module.get_accessory is original_module


async def test_patch_skips_unconfigured_entities(
    hass: HomeAssistant, hk_driver: object
) -> None:
    """Only entities in the include set become HeaterCooler; others fall through."""
    set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    hass.states.async_set(
        "climate.other",
        HVACMode.COOL,
        {
            ATTR_SUPPORTED_FEATURES: ClimateEntityFeature.FAN_MODE,
            ATTR_FAN_MODES: ["Auto", "Low", "High"],
            ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF],
        },
    )
    apply_patch(hass, {ENTITY_ID}, set())
    try:
        included = homekit_accessories.get_accessory(
            hass, hk_driver, hass.states.get(ENTITY_ID), 2, {}
        )
        other = homekit_accessories.get_accessory(
            hass, hk_driver, hass.states.get("climate.other"), 3, {}
        )
        assert type(included).__name__ == "HeaterCooler"
        assert type(other).__name__ == "Thermostat"
    finally:
        remove_patch(hass)


@pytest.mark.parametrize("core_shape", list(CORE_SHAPES))
async def test_patch_threads_configured_fan_lane(
    hass: HomeAssistant, hk_driver: object, core_shape: str
) -> None:
    """The configured fan lane reaches the accessory on either core generation."""
    set_climate(
        hass,
        HVACMode.COOL,
        **{
            ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF],
            ATTR_FAN_MODES: SEVEN_FAN_MODES,
        },
    )
    with CORE_SHAPES[core_shape]():
        apply_patch(hass, {ENTITY_ID}, set(), fan_lane=FAN_LANE_MANUAL)
        try:
            accessory = homekit_accessories.get_accessory(
                hass, hk_driver, hass.states.get(ENTITY_ID), 2, {}
            )
            # The manual lane must win; the default auto lane yields the /auto trio.
            assert accessory.ordered_fan_speeds == ["low", "mid", "high"]
        finally:
            remove_patch(hass)


async def test_patch_threads_configured_fan_entity(
    hass: HomeAssistant, hk_driver: object
) -> None:
    """A mapped fan entity reaches the accessory's config, keyed by climate id."""
    set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    hass.states.async_set(
        "climate.other",
        HVACMode.COOL,
        {
            ATTR_SUPPORTED_FEATURES: ClimateEntityFeature.FAN_MODE,
            ATTR_FAN_MODES: ["Auto", "Low", "High"],
            ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF],
        },
    )
    apply_patch(
        hass,
        {ENTITY_ID, "climate.other"},
        set(),
        fan_entities={ENTITY_ID: "fan.living"},
    )
    try:
        accessory = homekit_accessories.get_accessory(
            hass, hk_driver, hass.states.get(ENTITY_ID), 2, {}
        )
        assert accessory.fan_entity_id == "fan.living"

        # An unmapped included entity keeps deriving its fan from climate.
        other = homekit_accessories.get_accessory(
            hass, hk_driver, hass.states.get("climate.other"), 3, {}
        )
        assert other.fan_entity_id is None
    finally:
        remove_patch(hass)


async def test_apply_patch_updates_fan_entities_on_existing_state(
    hass: HomeAssistant, hk_driver: object
) -> None:
    """Re-applying the patch (e.g. an options update) refreshes the fan map."""
    set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    apply_patch(hass, {ENTITY_ID}, set())
    try:
        apply_patch(hass, {ENTITY_ID}, set(), fan_entities={ENTITY_ID: "fan.living"})
        accessory = homekit_accessories.get_accessory(
            hass, hk_driver, hass.states.get(ENTITY_ID), 2, {}
        )
        assert accessory.config[CONF_FAN_ENTITY_ID] == "fan.living"
    finally:
        remove_patch(hass)


async def test_patch_uses_bundled_type_without_touching_core_registry(
    hass: HomeAssistant, hk_driver: object
) -> None:
    """On a 2026.8 core we serve our own class and leave core's registration alone."""
    set_climate(
        hass,
        HVACMode.COOL,
        **{
            ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF],
            ATTR_FAN_MODES: SEVEN_FAN_MODES,
        },
    )
    with core_with_native():
        assert native_heatercooler_available() is True
        apply_patch(hass, {ENTITY_ID}, set(), fan_lane=FAN_LANE_MANUAL)
        try:
            accessory = homekit_accessories.get_accessory(
                hass, hk_driver, hass.states.get(ENTITY_ID), 2, {}
            )
            # Our accessory, carrying the lane core cannot represent.
            assert type(accessory).__module__.endswith("type_heatercooler")
            assert accessory.ordered_fan_speeds == ["low", "mid", "high"]
            # Core's own class must survive untouched for entities we never claimed.
            assert homekit_accessories.TYPES["HeaterCooler"] is _CoreHeaterCooler
        finally:
            remove_patch(hass)
        assert homekit_accessories.TYPES["HeaterCooler"] is _CoreHeaterCooler


async def test_apply_patch_no_op_on_signature_drift(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """A drifted HomeKit get_accessory signature must leave HomeKit untouched."""
    set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})

    def _drifted(
        hass: object,
        driver: object,
        state: object,
        aid: object,
        config: object,
        extra: object,
    ) -> None:
        return None

    with patch.object(homekit_accessories, "get_accessory", _drifted):
        caplog.clear()
        caplog.set_level(logging.WARNING)
        apply_patch(hass, {ENTITY_ID}, set())
        # The incompatible function must not be wrapped, and no patch state installed.
        assert homekit_accessories.get_accessory is _drifted
        assert DATA_PATCH_STATE not in hass.data.get(DOMAIN, {})
    assert any(
        record.levelno >= logging.WARNING and "signature changed" in record.getMessage()
        for record in caplog.records
    )


async def test_patch_falls_back_to_default_on_error(
    hass: HomeAssistant, hk_driver: object, caplog: pytest.LogCaptureFixture
) -> None:
    set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    apply_patch(hass, {ENTITY_ID}, set())

    def _raise(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    try:
        state = hass.states.get(ENTITY_ID)
        caplog.clear()
        caplog.set_level(logging.ERROR)
        with patch(
            "custom_components.homekit_heatercooler.type_heatercooler.HeaterCooler",
            _raise,
        ):
            accessory = homekit_accessories.get_accessory(hass, hk_driver, state, 2, {})
        assert type(accessory).__name__ == "Thermostat"
        # The failure must be surfaced, not swallowed silently.
        assert any(
            record.levelno >= logging.ERROR
            and "HeaterCooler mapping failed" in record.getMessage()
            for record in caplog.records
        )
    finally:
        remove_patch(hass)
