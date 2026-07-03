"""Fixtures for HomeKit HeaterCooler tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

import pytest

from homeassistant.components.homekit.accessories import HomeDriver
from homeassistant.components.homekit.const import BRIDGE_NAME
from homeassistant.components.homekit.iidmanager import AccessoryIIDStorage
from homeassistant.core import HomeAssistant


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations for all tests."""


@pytest.fixture
def iid_storage(hass: HomeAssistant) -> Generator[AccessoryIIDStorage]:
    """Return an iid storage that never writes to disk."""
    with patch.object(AccessoryIIDStorage, "_async_schedule_save"):
        yield AccessoryIIDStorage(hass, "")


@pytest.fixture
def hk_driver(
    hass: HomeAssistant, iid_storage: AccessoryIIDStorage
) -> Generator[HomeDriver]:
    """Return a HomeDriver suitable for constructing accessories in tests."""
    with (
        patch("pyhap.accessory_driver.AsyncZeroconf"),
        patch("pyhap.accessory_driver.AccessoryEncoder"),
        patch("pyhap.accessory_driver.HAPServer.async_stop"),
        patch("pyhap.accessory_driver.HAPServer.async_start"),
        patch("pyhap.accessory_driver.AccessoryDriver.publish"),
        patch("pyhap.accessory_driver.AccessoryDriver.persist"),
    ):
        yield HomeDriver(
            hass,
            pincode=b"123-45-678",
            entry_id="",
            entry_title="mock entry",
            bridge_name=BRIDGE_NAME,
            iid_storage=iid_storage,
            address="127.0.0.1",
            loop=hass.loop,
        )
