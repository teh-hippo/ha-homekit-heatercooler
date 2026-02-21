"""Enable HomeKit HeaterCooler mapping for selected climate entities."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entityfilter import CONF_EXCLUDE_ENTITIES, CONF_INCLUDE_ENTITIES

from .const import (
    DATA_YAML_EXCLUDE_ENTITIES,
    DATA_YAML_INCLUDE_ENTITIES,
    DOMAIN,
)
from .patcher import apply_patch

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_INCLUDE_ENTITIES, default=[]): vol.All(cv.ensure_list, [cv.entity_id]),
                vol.Optional(CONF_EXCLUDE_ENTITIES, default=[]): vol.All(cv.ensure_list, [cv.entity_id]),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: Mapping[str, Any]) -> bool:
    """Patch HomeKit climate selection and register HeaterCooler accessory."""
    include_entities, exclude_entities = _yaml_entities_from_config(config)
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data[DATA_YAML_INCLUDE_ENTITIES] = include_entities
    domain_data[DATA_YAML_EXCLUDE_ENTITIES] = exclude_entities
    _refresh_patch(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HomeKit HeaterCooler from a config entry."""
    entry.async_on_unload(entry.add_update_listener(_async_handle_entry_update))
    _refresh_patch(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a HomeKit HeaterCooler config entry."""
    _refresh_patch(hass)
    return True


async def _async_handle_entry_update(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle config entry updates."""
    _refresh_patch(hass)


def _yaml_entities_from_config(config: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    """Extract include/exclude entity IDs from YAML config."""
    integration_config = config.get(DOMAIN)
    if not isinstance(integration_config, Mapping):
        return set(), set()

    include_entities = _entity_set(integration_config.get(CONF_INCLUDE_ENTITIES))
    exclude_entities = _entity_set(integration_config.get(CONF_EXCLUDE_ENTITIES))
    return include_entities, exclude_entities


def _entry_entities(entry: ConfigEntry) -> tuple[set[str], set[str]]:
    """Extract include/exclude entity IDs from a config entry."""
    source = entry.options or entry.data
    include_entities = _entity_set(source.get(CONF_INCLUDE_ENTITIES))
    exclude_entities = _entity_set(source.get(CONF_EXCLUDE_ENTITIES))
    return include_entities, exclude_entities


def _entity_set(value: Any) -> set[str]:
    """Normalize config values to a set of entity IDs."""
    if not isinstance(value, (list, set, tuple)):
        return set()
    return {item for item in value if isinstance(item, str)}


def _refresh_patch(hass: HomeAssistant) -> None:
    """Apply patch with merged YAML and UI-configured entities."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    include_entities = _entity_set(domain_data.get(DATA_YAML_INCLUDE_ENTITIES))
    exclude_entities = _entity_set(domain_data.get(DATA_YAML_EXCLUDE_ENTITIES))

    for entry in hass.config_entries.async_entries(DOMAIN):
        entry_include_entities, entry_exclude_entities = _entry_entities(entry)
        include_entities.update(entry_include_entities)
        exclude_entities.update(entry_exclude_entities)

    apply_patch(hass, include_entities, exclude_entities)
    _LOGGER.info(
        "HomeKit HeaterCooler patch loaded (include_entities=%s, exclude_entities=%s)",
        sorted(include_entities),
        sorted(exclude_entities),
    )
