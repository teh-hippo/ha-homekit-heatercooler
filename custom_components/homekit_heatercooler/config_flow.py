"""Config flow for HomeKit HeaterCooler Bridge."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.helpers import selector
from homeassistant.helpers.entityfilter import CONF_EXCLUDE_ENTITIES, CONF_INCLUDE_ENTITIES

from .const import DOMAIN


def _normalize_entities(user_input: dict[str, Any]) -> dict[str, list[str]]:
    """Normalize and de-duplicate entity lists from user input."""
    include_entities = sorted(set(_list_of_strings(user_input.get(CONF_INCLUDE_ENTITIES))))
    exclude_entities = sorted(set(_list_of_strings(user_input.get(CONF_EXCLUDE_ENTITIES))))
    return {
        CONF_INCLUDE_ENTITIES: include_entities,
        CONF_EXCLUDE_ENTITIES: exclude_entities,
    }


def _list_of_strings(value: Any) -> list[str]:
    """Return only string items as a list."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _build_schema(include_entities: list[str], exclude_entities: list[str]) -> vol.Schema:
    """Build the form schema for include/exclude entities."""
    climate_selector = selector.EntitySelector(
        selector.EntitySelectorConfig(
            domain="climate",
            multiple=True,
        )
    )
    return vol.Schema(
        {
            vol.Required(CONF_INCLUDE_ENTITIES, default=include_entities): climate_selector,
            vol.Optional(CONF_EXCLUDE_ENTITIES, default=exclude_entities): climate_selector,
        }
    )


class HomeKitHeaterCoolerConfigFlow(ConfigFlow, domain=DOMAIN):  # type: ignore[misc, call-arg]
    """Handle config flow for HomeKit HeaterCooler Bridge."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> Any:
        """Handle the initial step."""
        if user_input is not None:
            return self.async_create_entry(
                title="HomeKit HeaterCooler Bridge",
                data=_normalize_entities(user_input),
            )

        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(include_entities=[], exclude_entities=[]),
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> Any:
        """Create the options flow."""
        return HomeKitHeaterCoolerOptionsFlow(config_entry)


class HomeKitHeaterCoolerOptionsFlow(OptionsFlow):  # type: ignore[misc]
    """Handle HomeKit HeaterCooler Bridge options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> Any:
        """Handle options."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data=_normalize_entities(user_input),
            )

        source = self.config_entry.options or self.config_entry.data
        include_entities = _list_of_strings(source.get(CONF_INCLUDE_ENTITIES))
        exclude_entities = _list_of_strings(source.get(CONF_EXCLUDE_ENTITIES))
        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(include_entities, exclude_entities),
        )
