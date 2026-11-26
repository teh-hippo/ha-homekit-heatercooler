"""Tests for Marketplace-installed integration translations."""

from __future__ import annotations

from custom_components.homekit_heatercooler.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations


async def test_english_translations_are_loadable(hass: HomeAssistant) -> None:
    """The custom integration ships the English translations Home Assistant loads."""
    config = await async_get_translations(hass, "en", "config", {DOMAIN})
    options = await async_get_translations(hass, "en", "options", {DOMAIN})
    selectors = await async_get_translations(hass, "en", "selector", {DOMAIN})

    assert (
        config[f"component.{DOMAIN}.config.step.user.data.include_entities"]
        == "Include entities"
    )
    assert (
        options[f"component.{DOMAIN}.options.step.init.data.fan_lane"]
        == "Fan slider mode"
    )
    assert (
        selectors[f"component.{DOMAIN}.selector.fan_lane.options.auto"]
        == "Auto - Low/Auto, Mid/Auto, High/Auto"
    )
