"""Enable HomeKit HeaterCooler mapping for selected climate entities."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entityfilter import CONF_EXCLUDE_ENTITIES, CONF_INCLUDE_ENTITIES

from .const import DOMAIN
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
    integration_config = config.get(DOMAIN, {})
    include_entities = set(integration_config.get(CONF_INCLUDE_ENTITIES, []))
    exclude_entities = set(integration_config.get(CONF_EXCLUDE_ENTITIES, []))

    apply_patch(hass, include_entities, exclude_entities)
    _LOGGER.info(
        "HomeKit HeaterCooler patch loaded (include_entities=%s, exclude_entities=%s)",
        sorted(include_entities),
        sorted(exclude_entities),
    )
    return True
