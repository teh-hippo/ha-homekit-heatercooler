"""Tests for config-entry setup and unload."""

from __future__ import annotations

from homeassistant.components.climate import ATTR_FAN_MODES, ATTR_HVAC_MODES, HVACMode
from homeassistant.const import ATTR_SUPPORTED_FEATURES
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entityfilter import CONF_INCLUDE_ENTITIES
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.homekit_heatercooler.const import (
    DATA_PATCH_STATE,
    DATA_PATCH_STATUS,
    DOMAIN,
)
from tests.common import ENTITY_ID, set_climate


async def test_setup_and_unload_installs_and_removes_patch(hass: HomeAssistant) -> None:
    """Setting up an entry installs the patch; unloading removes it."""
    set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_INCLUDE_ENTITIES: [ENTITY_ID]})
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert DATA_PATCH_STATE in hass.data[DOMAIN]

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert DATA_PATCH_STATE not in hass.data.get(DOMAIN, {})


async def test_setup_without_targets_does_not_install_patch(
    hass: HomeAssistant,
) -> None:
    """An entry with no include entities leaves HomeKit untouched."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_INCLUDE_ENTITIES: []})
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert DATA_PATCH_STATE not in hass.data.get(DOMAIN, {})


async def test_setup_survives_malformed_target_entity(hass: HomeAssistant) -> None:
    """A malformed supported_features must not break setup or diagnostics."""
    hass.states.async_set(
        "climate.broken",
        HVACMode.COOL,
        {
            ATTR_SUPPORTED_FEATURES: None,
            ATTR_FAN_MODES: ["low", "high"],
            ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF],
        },
    )
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_INCLUDE_ENTITIES: ["climate.broken"]}
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    status = hass.data[DOMAIN][DATA_PATCH_STATUS]
    assert "climate.broken" in status["unsupported_entities"]
    assert "climate.broken" not in status["patched_entities"]
