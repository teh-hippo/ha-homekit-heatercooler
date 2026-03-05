"""Enable HomeKit HeaterCooler mapping for selected climate entities."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import dispatcher_send
from homeassistant.helpers.entityfilter import CONF_EXCLUDE_ENTITIES, CONF_INCLUDE_ENTITIES
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import (
    DATA_PATCH_STATE,
    DATA_PATCH_STATUS,
    DATA_PATCH_STATUS_UNSUB,
    DATA_YAML_EXCLUDE_ENTITIES,
    DATA_YAML_INCLUDE_ENTITIES,
    DOMAIN,
    PLATFORMS,
    SIGNAL_PATCH_STATUS_UPDATED,
)
from .patcher import apply_patch, supports_heatercooler

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
    domain_data = _domain_data(hass)
    domain_data[DATA_YAML_INCLUDE_ENTITIES] = include_entities
    domain_data[DATA_YAML_EXCLUDE_ENTITIES] = exclude_entities
    _refresh_patch(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HomeKit HeaterCooler from a config entry."""
    entry.async_on_unload(entry.add_update_listener(_async_handle_entry_update))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _refresh_patch(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a HomeKit HeaterCooler config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    _refresh_patch(hass)
    return bool(unloaded)


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


def _domain_data(hass: HomeAssistant) -> dict[str, Any]:
    """Return mutable domain-scoped storage."""
    existing = hass.data.get(DOMAIN)
    if isinstance(existing, dict):
        return existing
    domain_data: dict[str, Any] = {}
    hass.data[DOMAIN] = domain_data
    return domain_data


def _refresh_patch(hass: HomeAssistant) -> None:
    """Apply patch with merged YAML and UI-configured entities."""
    domain_data = _domain_data(hass)
    include_entities, exclude_entities = _combined_entities(hass)
    apply_patch(hass, include_entities, exclude_entities)
    _register_patch_status_refresh(hass, include_entities, exclude_entities)
    _update_patch_status(hass, include_entities, exclude_entities)
    patch_status = domain_data[DATA_PATCH_STATUS]
    _LOGGER.info(
        "HomeKit HeaterCooler patch loaded (include_entities=%s, exclude_entities=%s, patched_entities=%s)",
        sorted(include_entities),
        sorted(exclude_entities),
        patch_status["patched_entities"],
    )


def _combined_entities(hass: HomeAssistant) -> tuple[set[str], set[str]]:
    """Collect include/exclude entities from YAML and config entries."""
    domain_data = _domain_data(hass)
    include_entities = _entity_set(domain_data.get(DATA_YAML_INCLUDE_ENTITIES))
    exclude_entities = _entity_set(domain_data.get(DATA_YAML_EXCLUDE_ENTITIES))

    for entry in hass.config_entries.async_entries(DOMAIN):
        entry_include_entities, entry_exclude_entities = _entry_entities(entry)
        include_entities.update(entry_include_entities)
        exclude_entities.update(entry_exclude_entities)

    return include_entities, exclude_entities


def _register_patch_status_refresh(
    hass: HomeAssistant,
    include_entities: set[str],
    exclude_entities: set[str],
) -> None:
    """Track status-relevant events and refresh diagnostics."""
    domain_data = _domain_data(hass)
    unsubscribe_previous = domain_data.get(DATA_PATCH_STATUS_UNSUB)
    if callable(unsubscribe_previous):
        unsubscribe_previous()

    target_entities = sorted(include_entities - exclude_entities)

    @callback  # type: ignore[untyped-decorator]
    def _handle_status_refresh(_: Event | None = None) -> None:
        current_include_entities, current_exclude_entities = _combined_entities(hass)
        _update_patch_status(hass, current_include_entities, current_exclude_entities)

    unsubscribe_state: Callable[[], None] | None = None
    if target_entities:
        unsubscribe_state = async_track_state_change_event(
            hass,
            target_entities,
            _handle_status_refresh,
        )

    unsubscribe_started: Callable[[], None] | None = None
    if not hass.is_running:
        unsubscribe_started = hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STARTED,
            _handle_status_refresh,
        )

    def _unsubscribe() -> None:
        if unsubscribe_state:
            unsubscribe_state()
        if unsubscribe_started:
            unsubscribe_started()

    domain_data[DATA_PATCH_STATUS_UNSUB] = _unsubscribe


def _update_patch_status(
    hass: HomeAssistant,
    include_entities: set[str],
    exclude_entities: set[str],
) -> None:
    """Recompute and publish patch diagnostics."""
    domain_data = _domain_data(hass)
    domain_data[DATA_PATCH_STATUS] = _build_patch_status(
        hass,
        include_entities,
        exclude_entities,
    )
    dispatcher_send(hass, SIGNAL_PATCH_STATUS_UPDATED)


def _build_patch_status(
    hass: HomeAssistant,
    include_entities: set[str],
    exclude_entities: set[str],
) -> dict[str, Any]:
    """Collect patch status details for diagnostic entities."""
    target_entities = sorted(include_entities - exclude_entities)
    patched_entities: list[str] = []
    missing_entities: list[str] = []
    unsupported_entities: list[str] = []
    non_climate_entities: list[str] = []

    for entity_id in target_entities:
        state = hass.states.get(entity_id)
        if state is None:
            missing_entities.append(entity_id)
            continue
        if state.domain != "climate":
            non_climate_entities.append(entity_id)
            continue
        if supports_heatercooler(state):
            patched_entities.append(entity_id)
            continue
        unsupported_entities.append(entity_id)

    hook_installed = bool(_domain_data(hass).get(DATA_PATCH_STATE))

    return {
        "patch_active": bool(patched_entities),
        "hook_installed": hook_installed,
        "include_entities": sorted(include_entities),
        "exclude_entities": sorted(exclude_entities),
        "target_entities": target_entities,
        "patched_entities": patched_entities,
        "currently_patchable_entities": patched_entities,
        "patched_entities_count": len(patched_entities),
        "missing_entities": missing_entities,
        "unsupported_entities": unsupported_entities,
        "non_climate_entities": non_climate_entities,
        "last_refresh": dt_util.utcnow().isoformat(),
    }
