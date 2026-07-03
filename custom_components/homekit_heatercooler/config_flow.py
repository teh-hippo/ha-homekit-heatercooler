"""Config flow for HomeKit HeaterCooler Bridge."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.helpers import selector
from homeassistant.helpers.entityfilter import (
    CONF_EXCLUDE_ENTITIES,
    CONF_INCLUDE_ENTITIES,
)

from .const import (
    CONF_FAN_LANE,
    DEFAULT_FAN_LANE,
    DOMAIN,
    FAN_LANE_AUTO,
    FAN_LANE_MANUAL,
)


def _normalize_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalize entity lists and fan lane from user input."""
    include_entities = sorted(
        set(_list_of_strings(user_input.get(CONF_INCLUDE_ENTITIES)))
    )
    exclude_entities = sorted(
        set(_list_of_strings(user_input.get(CONF_EXCLUDE_ENTITIES)))
    )
    lane = user_input.get(CONF_FAN_LANE)
    return {
        CONF_INCLUDE_ENTITIES: include_entities,
        CONF_EXCLUDE_ENTITIES: exclude_entities,
        CONF_FAN_LANE: lane
        if lane in (FAN_LANE_AUTO, FAN_LANE_MANUAL)
        else DEFAULT_FAN_LANE,
    }


def _list_of_strings(value: Any) -> list[str]:
    """Return only string items as a list."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _build_schema(
    include_entities: list[str], exclude_entities: list[str], fan_lane: str
) -> vol.Schema:
    """Build the form schema for include/exclude entities and fan lane."""
    climate_selector = selector.EntitySelector(
        selector.EntitySelectorConfig(
            domain="climate",
            multiple=True,
        )
    )
    return vol.Schema(
        {
            vol.Required(
                CONF_INCLUDE_ENTITIES, default=include_entities
            ): climate_selector,
            vol.Optional(
                CONF_EXCLUDE_ENTITIES, default=exclude_entities
            ): climate_selector,
            vol.Optional(CONF_FAN_LANE, default=fan_lane): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[FAN_LANE_AUTO, FAN_LANE_MANUAL],
                    translation_key=CONF_FAN_LANE,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


class HomeKitHeaterCoolerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle config flow for HomeKit HeaterCooler Bridge."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> Any:
        """Handle the initial step."""
        if user_input is not None:
            return self.async_create_entry(
                title="HomeKit HeaterCooler Bridge",
                data=_normalize_input(user_input),
            )

        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(
                include_entities=[], exclude_entities=[], fan_lane=DEFAULT_FAN_LANE
            ),
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> Any:
        """Create the options flow."""
        return HomeKitHeaterCoolerOptionsFlow()


class HomeKitHeaterCoolerOptionsFlow(OptionsFlow):
    """Handle HomeKit HeaterCooler Bridge options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> Any:
        """Handle options."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data=_normalize_input(user_input),
            )

        source = self.config_entry.options or self.config_entry.data
        include_entities = _list_of_strings(source.get(CONF_INCLUDE_ENTITIES))
        exclude_entities = _list_of_strings(source.get(CONF_EXCLUDE_ENTITIES))
        fan_lane = source.get(CONF_FAN_LANE, DEFAULT_FAN_LANE)
        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(include_entities, exclude_entities, fan_lane),
        )
