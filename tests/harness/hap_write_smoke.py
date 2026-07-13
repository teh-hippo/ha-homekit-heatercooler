#!/usr/bin/env python3
"""Verify a HeaterCooler HAP write reaches the disposable mock climate."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlparse
import urllib.request


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--harness-homekit",
        default=os.environ.get("HARNESS_HOMEKIT_DIR"),
        required=os.environ.get("HARNESS_HOMEKIT_DIR") is None,
        help="Path to ha-test-harness/homekit",
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
        help="Home Assistant token for the disposable instance",
    )
    parser.add_argument(
        "--device-id",
        default=os.environ.get("HC_DEVICE_ID"),
        required=os.environ.get("HC_DEVICE_ID") is None,
    )
    parser.add_argument(
        "--pin",
        default=os.environ.get("HC_PIN"),
        required=os.environ.get("HC_PIN") is None,
    )
    parser.add_argument("--ip", default=os.environ.get("HC_IP", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("HC_PORT", "21063"))
    )
    parser.add_argument(
        "--routing-mode",
        choices=("legacy", "native"),
        default=os.environ.get("HC_ROUTING_MODE", "legacy"),
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
    url: str, token: str, expected: str, timeout: float = 15
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


async def _run(args: argparse.Namespace) -> None:
    harness_homekit = Path(args.harness_homekit)
    sys.path.insert(0, str(harness_homekit))

    from aiohomekit import Controller
    from aiohomekit.characteristic_cache import CharacteristicCacheMemory
    from aiohomekit.model.characteristics import CharacteristicsTypes
    from aiohomekit.model.services import ServicesTypes
    from aiohomekit.uuid import normalize_uuid
    from aiohomekit.zeroconf import HAP_TYPE_TCP, ZeroconfServiceListener
    from smoke import (
        SVC_HEATER_COOLER,
        SVC_THERMOSTAT,
        discover_bridge,
        parse_accessories,
        register_pairing,
    )
    from zeroconf.asyncio import AsyncServiceBrowser, AsyncZeroconf

    alias = "heatercooler-write-smoke"
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
                discovery, _, _ = await discover_bridge(
                    controller, args.device_id, args.ip, args.port, 2, True
                )
                paired = False
                try:
                    finish_pairing = await discovery.async_start_pairing(alias)
                    pairing = await finish_pairing(args.pin)
                    register_pairing(controller, alias, pairing)
                    paired = True

                    accessories = parse_accessories(
                        await pairing.list_accessories_and_characteristics()
                    )
                    daikin = next(
                        (
                            accessory
                            for accessory in accessories
                            if accessory.name == "Mock Daikin"
                        ),
                        None,
                    )
                    thermostat = next(
                        (
                            accessory
                            for accessory in accessories
                            if accessory.name == "Mock Dual Swing"
                        ),
                        None,
                    )
                    if daikin is None or SVC_HEATER_COOLER not in daikin.services:
                        raise RuntimeError("Mock Daikin is not a HeaterCooler")
                    if thermostat is None or SVC_THERMOSTAT not in thermostat.services:
                        raise RuntimeError("Mock Dual Swing is not a Thermostat")

                    rotation_speed = normalize_uuid(CharacteristicsTypes.ROTATION_SPEED)
                    fan_v2 = normalize_uuid(ServicesTypes.FAN_V2)
                    rotation_on_heater_cooler = (
                        rotation_speed in daikin.services[SVC_HEATER_COOLER]
                    )
                    rotation_on_fan = (
                        fan_v2 in daikin.services
                        and rotation_speed in daikin.services[fan_v2]
                    )
                    if args.routing_mode == "legacy" and (
                        not rotation_on_heater_cooler or rotation_on_fan
                    ):
                        raise RuntimeError(
                            "Legacy route did not expose RotationSpeed on HeaterCooler"
                        )
                    if args.routing_mode == "native" and (
                        rotation_on_heater_cooler or not rotation_on_fan
                    ):
                        raise RuntimeError(
                            "Native route did not expose RotationSpeed on linked Fanv2"
                        )

                    target_iid = daikin.services[SVC_HEATER_COOLER][
                        normalize_uuid(CharacteristicsTypes.TARGET_HEATER_COOLER_STATE)
                    ][0]
                    await pairing.put_characteristics([(daikin.aid, target_iid, 2)])
                    await _wait_for_state(args.url, args.token, "cool")
                finally:
                    if paired:
                        await controller.remove_pairing(alias)
                    await discovery.close()
        finally:
            await browser.async_cancel()


def main() -> int:
    args = _parser().parse_args()
    asyncio.run(_run(args))
    print(f"HAP {args.routing_mode} route and target-mode write: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
