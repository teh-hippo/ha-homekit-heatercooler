"""Prove the already-paired upgrade assertions can actually fail.

``upgrade_smoke.sh`` needs containers and a real bridge, so it cannot run in the
unit suite. Its decisions are pure logic though, and a harness that only ever
passes proves nothing. These exercise each rejection directly.
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

HEATER_COOLER = "000000BC-0000-1000-8000-0026BB765291"
THERMOSTAT = "0000004A-0000-1000-8000-0026BB765291"
FAN_V2 = "000000B7-0000-1000-8000-0026BB765291"
SERVICES = {
    "heater_cooler": HEATER_COOLER,
    "thermostat": THERMOSTAT,
    "fan_v2": FAN_V2,
}


def _load() -> ModuleType:
    """Import the harness script by path; it is not an installed package."""
    path = Path(__file__).parent / "harness" / "hap_upgrade_smoke.py"
    spec = importlib.util.spec_from_file_location("hap_upgrade_smoke", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


upgrade = _load()


def _shape(*services: str, aid: int = 2) -> dict:
    return {"aid": aid, "services": {service: ["c1", "c2"] for service in services}}


def _args(scenario: str, config_number: int) -> argparse.Namespace:
    return argparse.Namespace(scenario=scenario, config_number=config_number)


def _check(
    scenario: str,
    before: dict,
    after: dict,
    before_config: int = 1,
    after_config: int = 2,
) -> None:
    upgrade._assert_after(
        _args(scenario, after_config),
        {"config_number": before_config, "shape": before},
        after,
        SERVICES,
        lambda service: service,
    )


def test_core_upgrade_accepts_an_unchanged_shape() -> None:
    shape = _shape(HEATER_COOLER)
    _check("core-upgrade", shape, shape)


def test_adopt_accepts_core_thermostat_replaced_by_ours() -> None:
    _check("adopt", _shape(THERMOSTAT, FAN_V2), _shape(HEATER_COOLER))


def test_adopt_accepts_core_heater_cooler_replaced_by_ours() -> None:
    """The 2026.8 starting point, where core already serves a HeaterCooler."""
    _check("adopt", _shape(HEATER_COOLER, FAN_V2), _shape(HEATER_COOLER))


def test_a_moved_accessory_id_is_rejected() -> None:
    with pytest.raises(RuntimeError, match="accessory id moved"):
        _check(
            "core-upgrade",
            _shape(HEATER_COOLER, aid=2),
            _shape(HEATER_COOLER, aid=3),
        )


def test_losing_the_heater_cooler_is_rejected() -> None:
    with pytest.raises(RuntimeError, match="no longer a HeaterCooler"):
        _check("adopt", _shape(THERMOSTAT), _shape(THERMOSTAT))


def test_a_surviving_thermostat_is_rejected() -> None:
    with pytest.raises(RuntimeError, match="Thermostat service survived"):
        _check("adopt", _shape(THERMOSTAT), _shape(HEATER_COOLER, THERMOSTAT))


def test_a_surviving_fan_tile_is_rejected() -> None:
    with pytest.raises(RuntimeError, match="linked Fanv2 survived"):
        _check("adopt", _shape(THERMOSTAT), _shape(HEATER_COOLER, FAN_V2))


def test_a_changed_shape_without_a_config_bump_is_rejected() -> None:
    """The stale tile itself: the database moved but nothing told the controller."""
    with pytest.raises(RuntimeError, match="config number did not advance"):
        _check(
            "adopt",
            _shape(THERMOSTAT, FAN_V2),
            _shape(HEATER_COOLER),
            before_config=4,
            after_config=4,
        )


def test_core_upgrade_rejects_a_changed_shape() -> None:
    with pytest.raises(RuntimeError, match="changed across a core upgrade"):
        _check("core-upgrade", _shape(HEATER_COOLER, FAN_V2), _shape(HEATER_COOLER))


def test_adopt_rejects_an_unchanged_shape() -> None:
    """A run that changed nothing would pass every other check silently."""
    shape = _shape(HEATER_COOLER)
    with pytest.raises(RuntimeError, match="did not change"):
        _check("adopt", shape, shape)


def test_adopt_rejects_a_starting_point_that_was_already_ours() -> None:
    """Without a core marker beforehand, the run never proved core was serving it."""
    before = _shape(HEATER_COOLER)
    after = {"aid": 2, "services": {HEATER_COOLER: ["c1", "c2", "c3"]}}
    with pytest.raises(RuntimeError, match="did not exercise the adoption path"):
        _check("adopt", before, after)
