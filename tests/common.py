"""Shared helpers for HomeKit HeaterCooler tests."""

from __future__ import annotations

from homeassistant.components.climate import (
    ATTR_FAN_MODES,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ClimateEntityFeature,
)
from homeassistant.const import ATTR_SUPPORTED_FEATURES
from homeassistant.core import HomeAssistant

ENTITY_ID = "climate.test"


def set_climate(hass: HomeAssistant, state: str, **extra: object) -> None:
    """Register a climate entity state with sensible HeaterCooler defaults."""
    attributes: dict[str, object] = {
        ATTR_SUPPORTED_FEATURES: ClimateEntityFeature.FAN_MODE,
        ATTR_FAN_MODES: ["Auto", "Low", "High"],
        ATTR_MIN_TEMP: 16,
        ATTR_MAX_TEMP: 30,
    }
    attributes.update(extra)
    hass.states.async_set(ENTITY_ID, state, attributes)
