#!/usr/bin/env python3
"""Prove that changing the accessory under an already-paired bridge is safe.

Apple Home only refetches an accessory database when the HAP configuration
number advances. If this integration swaps a climate entity from one service
type to another without that number moving, a controller keeps rendering the
old tile and the change is invisible. That is the failure this script exists to
catch.

It runs in two phases against the same Home Assistant config directory. The
``before`` phase pairs and records the accessory shape. The caller then changes
something, a core upgrade or the integration being installed, and restarts.
The ``after`` phase reconnects with the *persisted* pairing, never a fresh one,
and compares.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlparse
import urllib.request

ALIAS = "heatercooler-upgrade-smoke"
ACCESSORY_NAME = "Mock Daikin"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase",
        choices=("before", "after"),
        required=True,
        help="Pair and record, or reconnect and compare.",
    )
    parser.add_argument(
        "--scenario",
        choices=("core-upgrade", "adopt"),
        required=True,
        help=(
            "core-upgrade: the same integration across a core change, so the "
            "shape must hold. adopt: core's own accessory replaced by ours, so "
            "the shape must change and the config number must move with it."
        ),
    )
    parser.add_argument(
        "--snapshot",
        required=True,
        help="Where the before phase records the shape for the after phase.",
    )
    parser.add_argument(
        "--config-number",
        type=int,
        required=True,
        help="HAP config number (c#) read from the bridge state file.",
    )
    parser.add_argument(
        "--harness-homekit",
        default=os.environ.get("HARNESS_HOMEKIT_DIR"),
        required=os.environ.get("HARNESS_HOMEKIT_DIR") is None,
        help="Path to ha-test-harness/homekit",
    )
    parser.add_argument(
        "--pairing-file",
        default=os.environ.get("HC_PAIRING_FILE"),
        required=os.environ.get("HC_PAIRING_FILE") is None,
        help="Where the pairing persists between the two phases.",
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("HA_URL"),
        required=os.environ.get("HA_URL") is None,
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("HA_TOKEN"),
        required=os.environ.get("HA_TOKEN") is None,
    )
    parser.add_argument(
        "--device-id",
        default=os.environ.get("HC_DEVICE_ID"),
        required=os.environ.get("HC_DEVICE_ID") is None,
    )
    parser.add_argument("--pin", default=os.environ.get("HC_PIN"))
    parser.add_argument("--ip", default=os.environ.get("HC_IP", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("HC_PORT", "21063"))
    )
    return parser


def _read_state(url: str, token: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Home Assistant URL must be an absolute HTTP(S) URL")
    request = urllib.request.Request(  # noqa: S310 - URL scheme is constrained above.
        f"{url.rstrip('/')}/api/states/climate.mock_daikin",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(  # noqa: S310 - URL scheme is constrained above.
        request, timeout=15
    ) as response:
        return json.loads(response.read())["state"]


async def _wait_for_state(
    url: str, token: str, expected: str, timeout: float = 20
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    last_state: str | None = None
    while loop.time() < deadline:
        last_state = await asyncio.to_thread(_read_state, url, token)
        if last_state == expected:
            return
        await asyncio.sleep(0.25)
    raise RuntimeError(f"Mock Daikin state was {last_state!r}, expected {expected!r}")


def _shape(accessory: Any) -> dict[str, Any]:
    """Reduce an accessory to the parts a controller renders.

    Instance ids are deliberately excluded. They are free to move across a
    restart, and holding them constant would fail for a reason that has nothing
    to do with a stranded tile.
    """
    return {
        "aid": accessory.aid,
        "services": {
            service: sorted(chars)
            for service, chars in sorted(accessory.services.items())
        },
    }


def _diff(before: dict[str, Any], after: dict[str, Any], svc_label: Any) -> str:
    """Describe how two shapes differ, so a failure is diagnosable."""
    lines: list[str] = []
    services_before = before["services"]
    services_after = after["services"]
    for service in sorted(set(services_before) | set(services_after)):
        label = svc_label(service)
        if service not in services_after:
            lines.append(f"  - {label} removed")
        elif service not in services_before:
            lines.append(f"  + {label} added")
        elif services_before[service] != services_after[service]:
            gone = set(services_before[service]) - set(services_after[service])
            new = set(services_after[service]) - set(services_before[service])
            lines.append(f"  ~ {label} chars -{len(gone)} +{len(new)}")
    return "\n".join(lines) or "  (no service level difference)"


def _describe(shape: dict[str, Any], svc_label: Any) -> str:
    return ", ".join(
        f"{svc_label(service)}({len(chars)} chars)"
        for service, chars in shape["services"].items()
    )


async def _list_accessories(pairing: Any, attempts: int = 10) -> Any:
    """Read the accessory database, tolerating a bridge that just restarted.

    Only the initial connection is retried. A failure to read after the bridge
    answers is a real failure and is allowed through.
    """
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return await pairing.list_accessories_and_characteristics()
        except Exception as err:  # noqa: BLE001 - re-raised below once out of attempts.
            last = err
            await asyncio.sleep(2 if attempt else 0.5)
    raise RuntimeError(f"could not read the accessory database: {last}")


async def _run(args: argparse.Namespace) -> None:
    sys.path.insert(0, str(Path(args.harness_homekit)))

    from aiohomekit import Controller
    from aiohomekit.characteristic_cache import CharacteristicCacheMemory
    from aiohomekit.model.services import ServicesTypes
    from aiohomekit.uuid import normalize_uuid
    from aiohomekit.zeroconf import HAP_TYPE_TCP, ZeroconfServiceListener
    from smoke import SVC_HEATER_COOLER, SVC_THERMOSTAT, svc_label
    from zeroconf.asyncio import AsyncServiceBrowser, AsyncZeroconf

    services = {
        "heater_cooler": SVC_HEATER_COOLER,
        "thermostat": SVC_THERMOSTAT,
        "fan_v2": normalize_uuid(ServicesTypes.FAN_V2),
    }
    snapshot_path = Path(args.snapshot)

    # The controller needs a zeroconf instance even though both phases reach the
    # bridge by address; discovery is only used for the initial pair-setup.
    async with AsyncZeroconf() as zeroconf:
        listener = ZeroconfServiceListener()
        browser = AsyncServiceBrowser(
            zeroconf.zeroconf,
            [HAP_TYPE_TCP, "_hap._udp.local."],
            listener=listener,
        )
        controller = Controller(
            async_zeroconf_instance=zeroconf,
            char_cache=CharacteristicCacheMemory(),
        )
        try:
            async with controller:
                await _phase(args, controller, snapshot_path, services, svc_label)
        finally:
            await browser.async_cancel()


async def _phase(
    args: argparse.Namespace,
    controller: Any,
    snapshot_path: Path,
    services: dict[str, str],
    svc_label: Any,
) -> None:
    """Run one side of the upgrade against an already-started controller."""
    from aiohomekit.model.characteristics import CharacteristicsTypes
    from aiohomekit.uuid import normalize_uuid
    from smoke import discover_bridge, parse_accessories, register_pairing

    heater_cooler = services["heater_cooler"]

    controller.load_data(args.pairing_file)

    if args.phase == "before":
        if ALIAS in controller.aliases:
            raise RuntimeError(
                f"{args.pairing_file} already holds {ALIAS!r}; the before "
                "phase must start from an unpaired bridge"
            )
        if not args.pin:
            raise RuntimeError("--pin is required for the before phase")
        discovery, _, _ = await discover_bridge(
            controller, args.device_id, args.ip, args.port, 2, True
        )
        try:
            finish_pairing = await discovery.async_start_pairing(ALIAS)
            pairing = await finish_pairing(args.pin)
            register_pairing(controller, ALIAS, pairing)
            controller.save_data(args.pairing_file)
        finally:
            await discovery.close()
    else:
        # Reconnecting from persisted data is the whole point. A fresh
        # pair-setup here would rebuild the controller's view of the bridge
        # and hide exactly the staleness being tested for.
        pairing = controller.aliases.get(ALIAS)
        if pairing is None:
            raise RuntimeError(
                f"no persisted pairing {ALIAS!r} in {args.pairing_file}; the "
                "bridge dropped the pairing across the change"
            )

    try:
        accessories = parse_accessories(await _list_accessories(pairing))
        target = next((a for a in accessories if a.name == ACCESSORY_NAME), None)
        if target is None:
            raise RuntimeError(f"{ACCESSORY_NAME} is not on the bridge")
        shape = _shape(target)
        print(f"[{args.phase}] c#={args.config_number} {_describe(shape, svc_label)}")

        if args.phase == "before":
            snapshot_path.write_text(
                json.dumps({"config_number": args.config_number, "shape": shape}),
                encoding="utf-8",
            )
            print(f"[before] recorded to {snapshot_path}")
            return

        recorded = json.loads(snapshot_path.read_text(encoding="utf-8"))
        _assert_after(args, recorded, shape, services, svc_label)

        target_iid = target.services[heater_cooler][
            normalize_uuid(CharacteristicsTypes.TARGET_HEATER_COOLER_STATE)
        ][0]
        await pairing.put_characteristics([(target.aid, target_iid, 2)])
        await _wait_for_state(args.url, args.token, "cool")
        print("[after] a write on the reused pairing still reaches the entity")
    finally:
        if args.phase == "after":
            await controller.remove_pairing(ALIAS)
            controller.save_data(args.pairing_file)


def _assert_after(
    args: argparse.Namespace,
    recorded: dict[str, Any],
    shape: dict[str, Any],
    services: dict[str, str],
    svc_label: Any,
) -> None:
    """Check the contract a controller relies on after the change."""
    before_shape = recorded["shape"]
    before_config = recorded["config_number"]
    changed = before_shape != shape
    heater_cooler = services["heater_cooler"]
    thermostat = services["thermostat"]
    fan_v2 = services["fan_v2"]

    if shape["aid"] != before_shape["aid"]:
        raise RuntimeError(
            f"accessory id moved from {before_shape['aid']} to {shape['aid']}; a "
            "controller would show this as a new and a stranded accessory"
        )

    # The shape this integration always serves, matching hap_write_smoke.
    if heater_cooler not in shape["services"]:
        raise RuntimeError("the entity is no longer a HeaterCooler")
    if thermostat in shape["services"]:
        raise RuntimeError(
            "a Thermostat service survived alongside the HeaterCooler; the "
            "previous shape was not fully replaced"
        )
    if fan_v2 in shape["services"]:
        raise RuntimeError(
            "a linked Fanv2 survived; core's fan tile was not replaced by ours"
        )

    # The refetch contract. A controller has no other signal that the database
    # moved, so a changed shape with a static config number is a stranded tile.
    if changed and args.config_number <= before_config:
        raise RuntimeError(
            "accessory shape changed but the config number did not advance "
            f"({before_config} -> {args.config_number}); a paired controller "
            "would keep rendering the old tile.\n"
            + _diff(before_shape, shape, svc_label)
        )

    if args.scenario == "core-upgrade" and changed:
        raise RuntimeError(
            "the accessory shape changed across a core upgrade; the integration "
            "is meant to serve the same accessory on either generation.\n"
            + _diff(before_shape, shape, svc_label)
        )

    if args.scenario == "adopt":
        if not changed:
            raise RuntimeError(
                "the accessory shape did not change after installing the "
                "integration, so the test proved nothing"
            )
        # Core serves a Thermostat on 2026.7 and its own HeaterCooler with a
        # linked fan tile on 2026.8. Requiring one of those before the swap is
        # how this run proves it started from core's accessory and not ours,
        # without needing to know which generation it is on.
        core_markers = {thermostat, fan_v2} & set(before_shape["services"])
        if not core_markers:
            raise RuntimeError(
                "the starting accessory carried neither a Thermostat nor a "
                "linked Fanv2, so core was not serving it and this run did not "
                "exercise the adoption path"
            )

    print(
        f"[after] shape {'changed' if changed else 'held'}, "
        f"c# {before_config} -> {args.config_number}"
    )
    if changed:
        print(_diff(before_shape, shape, svc_label))


def main() -> int:
    args = _parser().parse_args()
    asyncio.run(_run(args))
    if args.phase == "after":
        print(f"Already-paired {args.scenario} upgrade: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
