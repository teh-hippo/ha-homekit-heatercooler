"""Runtime patching for Home Assistant HomeKit accessory selection."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import inspect
import logging
from typing import Any

from homeassistant.components import homekit as homekit_module
from homeassistant.components.climate import (
    ATTR_FAN_MODES,
    ATTR_SWING_MODES,
    ClimateEntityFeature,
)
from homeassistant.components.homekit import accessories as homekit_accessories
from homeassistant.const import ATTR_SUPPORTED_FEATURES, CONF_NAME
from homeassistant.core import HomeAssistant, State

from . import type_heatercooler as _type_heatercooler  # noqa: F401
from .climate_util import as_float
from .const import CONF_FAN_LANE, DATA_PATCH_STATE, DEFAULT_FAN_LANE, DOMAIN

_LOGGER = logging.getLogger(__name__)

EXPECTED_GET_ACCESSORY_PARAMS = ("hass", "driver", "state", "aid", "config")

GetAccessory = Callable[
    [HomeAssistant, homekit_accessories.HomeDriver, State, int | None, dict[Any, Any]],
    homekit_accessories.HomeAccessory | None,
]


@dataclass
class PatchState:
    """In-memory runtime patch state."""

    include_entities: set[str]
    exclude_entities: set[str]
    fan_lane: str
    original_get_accessory: GetAccessory
    original_homekit_get_accessory: GetAccessory


def supports_heatercooler(state: State) -> bool:
    """Return True if a climate entity has capabilities suited to HeaterCooler."""
    features_value = as_float(state.attributes.get(ATTR_SUPPORTED_FEATURES, 0))
    features = int(features_value) if features_value is not None else 0
    supports_fan_or_swing = bool(
        features & ClimateEntityFeature.FAN_MODE
        or features & ClimateEntityFeature.SWING_MODE
    )
    has_modes = bool(
        state.attributes.get(ATTR_FAN_MODES) or state.attributes.get(ATTR_SWING_MODES)
    )
    return supports_fan_or_swing and has_modes


def _should_patch_entity(
    entity_id: str, include_entities: set[str], exclude_entities: set[str]
) -> bool:
    """Return True when this entity should be redirected to HeaterCooler."""
    return (
        bool(include_entities)
        and entity_id in include_entities
        and entity_id not in exclude_entities
    )


def _get_accessory_params(func: Callable[..., Any]) -> tuple[str, ...]:
    """Return the parameter names of HomeKit's get_accessory, or () if unavailable."""
    try:
        return tuple(inspect.signature(func).parameters)
    except Exception:
        return ()


def apply_patch(
    hass: HomeAssistant,
    include_entities: set[str],
    exclude_entities: set[str],
    fan_lane: str = DEFAULT_FAN_LANE,
) -> None:
    """Patch HomeKit get_accessory to expose selected climates as HeaterCooler."""
    if "HeaterCooler" not in homekit_accessories.TYPES:
        _LOGGER.error(
            "HeaterCooler accessory type is not registered; leaving HomeKit untouched"
        )
        return

    domain_data = hass.data.setdefault(DOMAIN, {})
    patch_state = domain_data.get(DATA_PATCH_STATE)
    if patch_state:
        patch_state.include_entities = include_entities
        patch_state.exclude_entities = exclude_entities
        patch_state.fan_lane = fan_lane
        return

    original_get_accessory = homekit_accessories.get_accessory
    original_homekit_get_accessory = homekit_module.get_accessory
    actual_params = _get_accessory_params(original_get_accessory)
    if actual_params != EXPECTED_GET_ACCESSORY_PARAMS:
        _LOGGER.warning(
            "HomeKit get_accessory signature changed to %s; leaving HomeKit untouched",
            actual_params,
        )
        return

    patch_state = PatchState(
        include_entities=include_entities,
        exclude_entities=exclude_entities,
        fan_lane=fan_lane,
        original_get_accessory=original_get_accessory,
        original_homekit_get_accessory=original_homekit_get_accessory,
    )

    def patched_get_accessory(
        hass: HomeAssistant,
        driver: homekit_accessories.HomeDriver,
        state: State,
        aid: int | None,
        config: dict[Any, Any],
    ) -> homekit_accessories.HomeAccessory | None:
        config = config or {}
        try:
            if (
                state.domain == "climate"
                and aid
                and _should_patch_entity(
                    state.entity_id,
                    patch_state.include_entities,
                    patch_state.exclude_entities,
                )
                and supports_heatercooler(state)
            ):
                name = config.get(CONF_NAME, state.name)
                hc_config = {**config, CONF_FAN_LANE: patch_state.fan_lane}
                return homekit_accessories.TYPES["HeaterCooler"](
                    hass, driver, name, state.entity_id, aid, hc_config
                )
        except Exception:
            _LOGGER.exception(
                "HeaterCooler mapping failed for %s; falling back to the "
                "default accessory",
                state.entity_id,
            )

        return patch_state.original_get_accessory(hass, driver, state, aid, config)

    homekit_accessories.get_accessory = patched_get_accessory
    homekit_module.get_accessory = patched_get_accessory
    domain_data[DATA_PATCH_STATE] = patch_state
    _LOGGER.debug("Installed HeaterCooler get_accessory patch")


def remove_patch(hass: HomeAssistant) -> None:
    """Restore the original HomeKit get_accessory functions."""
    domain_data = hass.data.get(DOMAIN)
    if not isinstance(domain_data, dict):
        return
    patch_state = domain_data.pop(DATA_PATCH_STATE, None)
    if patch_state is None:
        return
    homekit_accessories.get_accessory = patch_state.original_get_accessory
    homekit_module.get_accessory = patch_state.original_homekit_get_accessory
    _LOGGER.debug("Removed HeaterCooler get_accessory patch")
