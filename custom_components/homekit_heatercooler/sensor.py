"""Diagnostic sensors for HomeKit HeaterCooler Bridge."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_PATCH_STATUS, DOMAIN, SIGNAL_PATCH_STATUS_UPDATED


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up diagnostic entities for a config entry."""
    async_add_entities([HomeKitHeaterCoolerPatchedEntitiesSensor(entry)])


class HomeKitHeaterCoolerPatchedEntitiesSensor(SensorEntity):  # type: ignore[misc]
    """Show how many selected entities are currently patched."""

    _attr_has_entity_name = True
    _attr_name = "Patched entities"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:air-conditioner"

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the diagnostic sensor."""
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_patched_entities"

    @property
    def native_value(self) -> int:
        """Return number of entities currently eligible for HeaterCooler patching."""
        return int(self._patch_status.get("patched_entities_count", 0))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return patch diagnostics."""
        status = self._patch_status
        return {
            "patch_active": bool(status.get("patch_active", False)),
            "include_entities": status.get("include_entities", []),
            "exclude_entities": status.get("exclude_entities", []),
            "target_entities": status.get("target_entities", []),
            "patched_entities": status.get("patched_entities", []),
            "missing_entities": status.get("missing_entities", []),
            "unsupported_entities": status.get("unsupported_entities", []),
            "non_climate_entities": status.get("non_climate_entities", []),
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return integration device metadata for UI grouping."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="HomeKit HeaterCooler Bridge",
            manufacturer="Home Assistant",
            model="HeaterCooler patch",
            configuration_url="https://github.com/teh-hippo/ha-homekit-heatercooler",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to runtime patch updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_PATCH_STATUS_UPDATED,
                self._handle_patch_status_update,
            )
        )

    def _handle_patch_status_update(self) -> None:
        """Write updated patch status to Home Assistant state."""
        self.async_write_ha_state()

    @property
    def _patch_status(self) -> dict[str, Any]:
        """Return current patch diagnostics from shared domain data."""
        hass = getattr(self, "hass", None)
        if hass is None:
            return {}
        domain_data = hass.data.get(DOMAIN)
        if not isinstance(domain_data, dict):
            return {}
        status = domain_data.get(DATA_PATCH_STATUS)
        if not isinstance(status, dict):
            return {}
        return status
