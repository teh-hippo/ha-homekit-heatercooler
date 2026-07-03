"""Tests for the diagnostic patched-entities sensor."""

from __future__ import annotations

from homeassistant.components.climate import ATTR_HVAC_MODES, HVACMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entityfilter import CONF_INCLUDE_ENTITIES
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.homekit_heatercooler.const import DOMAIN
from tests.common import ENTITY_ID, set_climate


async def test_sensor_reports_patch_diagnostics(hass: HomeAssistant) -> None:
    """The sensor counts patchable entities and buckets missing/non-climate targets."""
    set_climate(hass, HVACMode.COOL, **{ATTR_HVAC_MODES: [HVACMode.COOL, HVACMode.OFF]})
    hass.states.async_set("sensor.not_climate", "1")
    # climate.missing is intentionally never registered so it lands in missing_entities.
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_INCLUDE_ENTITIES: [ENTITY_ID, "sensor.not_climate", "climate.missing"]
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_patched_entities"
    )
    assert entity_id
    state = hass.states.get(entity_id)
    assert state is not None

    # native_value counts only the currently patchable entity.
    assert state.state == "1"
    assert state.attributes["patched_entities"] == [ENTITY_ID]
    assert state.attributes["non_climate_entities"] == ["sensor.not_climate"]
    assert state.attributes["missing_entities"] == ["climate.missing"]
    assert state.attributes["patch_active"] is True
    assert state.attributes["hook_installed"] is True
