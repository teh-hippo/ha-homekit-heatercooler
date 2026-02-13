"""Runtime patching for Home Assistant HomeKit accessory selection."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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

from .const import DATA_PATCH_STATE, DOMAIN
from .type_heatercooler import register_heatercooler_type


@dataclass
class PatchState:
    """In-memory runtime patch state."""

    include_entities: set[str]
    exclude_entities: set[str]
    original_get_accessory: Callable[..., Any]
    original_homekit_get_accessory: Callable[..., Any]


def _supports_heatercooler(state: State) -> bool:
    """Return True if a climate entity has capabilities suited to HeaterCooler."""
    features = int(state.attributes.get(ATTR_SUPPORTED_FEATURES, 0))
    supports_fan_or_swing = bool(features & ClimateEntityFeature.FAN_MODE or features & ClimateEntityFeature.SWING_MODE)
    has_modes = bool(state.attributes.get(ATTR_FAN_MODES) or state.attributes.get(ATTR_SWING_MODES))
    return supports_fan_or_swing and has_modes


def _should_patch_entity(entity_id: str, include_entities: set[str], exclude_entities: set[str]) -> bool:
    """Return True when this entity should be redirected to HeaterCooler."""
    if entity_id in exclude_entities:
        return False
    if not include_entities:
        return False
    return entity_id in include_entities


def apply_patch(hass: HomeAssistant, include_entities: set[str], exclude_entities: set[str]) -> None:
    """Patch HomeKit get_accessory to expose selected climates as HeaterCooler."""
    register_heatercooler_type()

    domain_data = hass.data.setdefault(DOMAIN, {})
    patch_state = domain_data.get(DATA_PATCH_STATE)
    if patch_state:
        patch_state.include_entities = include_entities
        patch_state.exclude_entities = exclude_entities
        return

    original_get_accessory = homekit_accessories.get_accessory
    original_homekit_get_accessory = homekit_module.get_accessory
    patch_state = PatchState(
        include_entities=include_entities,
        exclude_entities=exclude_entities,
        original_get_accessory=original_get_accessory,
        original_homekit_get_accessory=original_homekit_get_accessory,
    )

    def patched_get_accessory(
        hass_obj: HomeAssistant,
        driver: homekit_accessories.HomeDriver,
        state: State,
        aid: int | None,
        config: dict[str, Any] | None,
    ) -> homekit_accessories.HomeAccessory | None:
        config = config or {}
        if (
            state.domain == "climate"
            and aid
            and _should_patch_entity(
                state.entity_id,
                patch_state.include_entities,
                patch_state.exclude_entities,
            )
            and _supports_heatercooler(state)
        ):
            name = config.get(CONF_NAME, state.name)
            return homekit_accessories.TYPES["HeaterCooler"](hass_obj, driver, name, state.entity_id, aid, config)

        return patch_state.original_get_accessory(hass_obj, driver, state, aid, config)

    homekit_accessories.get_accessory = patched_get_accessory
    homekit_module.get_accessory = patched_get_accessory
    domain_data[DATA_PATCH_STATE] = patch_state
