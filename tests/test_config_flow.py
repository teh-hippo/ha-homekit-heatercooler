"""Tests for the HomeKit HeaterCooler config and options flow."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.entityfilter import (
    CONF_EXCLUDE_ENTITIES,
    CONF_INCLUDE_ENTITIES,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.homekit_heatercooler.config_flow import _normalize_input
from custom_components.homekit_heatercooler.const import (
    CONF_FAN_LANE,
    DEFAULT_FAN_LANE,
    DOMAIN,
    FAN_LANE_AUTO,
    FAN_LANE_MANUAL,
)


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    """The user flow normalises input and creates an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_INCLUDE_ENTITIES: ["climate.living", "climate.bedroom"],
            CONF_EXCLUDE_ENTITIES: [],
            CONF_FAN_LANE: FAN_LANE_MANUAL,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_INCLUDE_ENTITIES] == [
        "climate.bedroom",
        "climate.living",
    ]
    assert result["data"][CONF_FAN_LANE] == FAN_LANE_MANUAL


async def test_options_flow_round_trip(hass: HomeAssistant) -> None:
    """The options flow updates the stored include list and fan lane."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_INCLUDE_ENTITIES: ["climate.a"],
            CONF_EXCLUDE_ENTITIES: [],
            CONF_FAN_LANE: FAN_LANE_AUTO,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_INCLUDE_ENTITIES: ["climate.b"],
            CONF_EXCLUDE_ENTITIES: [],
            CONF_FAN_LANE: FAN_LANE_MANUAL,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_INCLUDE_ENTITIES] == ["climate.b"]
    assert result["data"][CONF_FAN_LANE] == FAN_LANE_MANUAL


def test_normalize_input_sorts_dedupes_and_filters() -> None:
    """Non-string entries are dropped and the lists are sorted and de-duplicated."""
    normalized = _normalize_input(
        {
            CONF_INCLUDE_ENTITIES: ["climate.b", "climate.a", "climate.a", 123, None],
            CONF_EXCLUDE_ENTITIES: ["climate.z", "climate.z"],
            CONF_FAN_LANE: FAN_LANE_MANUAL,
        }
    )
    assert normalized[CONF_INCLUDE_ENTITIES] == ["climate.a", "climate.b"]
    assert normalized[CONF_EXCLUDE_ENTITIES] == ["climate.z"]
    assert normalized[CONF_FAN_LANE] == FAN_LANE_MANUAL


def test_normalize_input_invalid_fan_lane_falls_back() -> None:
    """An unknown or missing fan lane resolves to the default."""
    assert (
        _normalize_input({CONF_INCLUDE_ENTITIES: [], CONF_FAN_LANE: "bogus"})[
            CONF_FAN_LANE
        ]
        == DEFAULT_FAN_LANE
    )
    assert (
        _normalize_input({CONF_INCLUDE_ENTITIES: []})[CONF_FAN_LANE] == DEFAULT_FAN_LANE
    )
