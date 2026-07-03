#!/usr/bin/env python3
"""Project the custom component's two shared files into Home Assistant core layout.

The custom component (CC) and the upstream core fork share two files verbatim:

    custom_components/homekit_heatercooler/type_heatercooler.py
    custom_components/homekit_heatercooler/climate_util.py

They are byte-identical to the core fork's copies
(homeassistant/components/homekit/{type_heatercooler,climate_util}.py) EXCEPT for
one small, documented, irreducible delta. This script rewrites the CC copies into
the core layout by applying ONLY that delta, so a port stays a mechanical
"project + copy + wire" operation.

The irreducible delta (see files/minimise-delta.md and
files/dual-purpose-architecture.md in the Workstream D session notes):

  1. Absolute -> relative imports. The CC imports its sibling core modules
     absolutely because `.accessories`/`.util` do not exist inside the CC package:
         from homeassistant.components.homekit.accessories import TYPES, HomeAccessory
         from homeassistant.components.homekit.util import temperature_to_states
         from homeassistant.components.homekit.util import temperature_to_homekit
     Inside core these are relative (`from .accessories import ...`,
     `from .util import ...`).

  2. The CC-only `fan_lane` extension. The CC lets a user pick the manual fan
     slider ordering via a `fan_lane` config option; core auto-detects the AUTO
     lane and does not carry this option. The extension is intentionally NOT
     upstreamed, so projecting to core strips it.

Each transform below is a literal (old -> new) block replacement. `old` must
appear EXACTLY once in the source; if it appears zero or many times the CC file
has drifted from the shape this transform encodes and the script fails loudly so
a human updates the transform. That failure is the intended drift signal.

Usage:
    port_to_core.py --out <dir>       Write the projected files into <dir>.
    port_to_core.py --check <coredir> Project in-memory and assert the result is
                                      byte-identical to the files in <coredir>;
                                      exit non-zero and print a diff on mismatch.

Self-test / correctness proof: `--check` against the core fork's shared files
(homeassistant/components/homekit) MUST pass byte-exactly. If it does not, the
transform no longer reproduces the fork and must be fixed.

Stdlib-only by design so it can run anywhere (CI, a bare checkout) with no deps.
"""

import argparse
import difflib
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
CC_DIR = REPO_ROOT / "custom_components" / "homekit_heatercooler"

# The two files shared verbatim (modulo the delta below) between CC and core.
SHARED_FILES = ("type_heatercooler.py", "climate_util.py")

# Per-file ordered list of (description, old, new) literal replacements that
# encode the entire irreducible CC -> core delta. Keep these minimal: each entry
# maps one documented difference. `old` must match exactly once.
Transform = tuple[str, str, str]

TRANSFORMS: dict[str, list[Transform]] = {
    "type_heatercooler.py": [
        (
            "imports: drop absolute homekit imports (re-added relative below)",
            (
                "from homeassistant.components.homekit.accessories import "
                "TYPES, HomeAccessory\n"
                "from homeassistant.components.homekit.util import "
                "temperature_to_states\n"
                "from homeassistant.const import (\n"
            ),
            "from homeassistant.const import (\n",
        ),
        (
            "imports: add relative .accessories import",
            (
                "from homeassistant.util.enum import try_parse_enum\n"
                "\n"
                "from .climate_util import (\n"
            ),
            (
                "from homeassistant.util.enum import try_parse_enum\n"
                "\n"
                "from .accessories import TYPES, HomeAccessory\n"
                "from .climate_util import (\n"
            ),
        ),
        (
            "fan_lane: drop CONF_FAN_LANE/DEFAULT_FAN_LANE from the .const import",
            (
                "    CHAR_TARGET_HEATER_COOLER_STATE,\n"
                "    CONF_FAN_LANE,\n"
                "    DEFAULT_FAN_LANE,\n"
                "    PROP_MAX_VALUE,\n"
            ),
            ("    CHAR_TARGET_HEATER_COOLER_STATE,\n    PROP_MAX_VALUE,\n"),
        ),
        (
            "imports: add relative .util import after the .const block",
            "    SERV_HEATER_COOLER,\n)\n",
            "    SERV_HEATER_COOLER,\n)\nfrom .util import temperature_to_states\n",
        ),
        (
            "fan_lane: drop the lane lookup and the lane arg to build_fan_speed_map",
            (
                "        if features & ClimateEntityFeature.FAN_MODE and "
                "fan_mode_names:\n"
                "            lane = self.config.get(CONF_FAN_LANE, "
                "DEFAULT_FAN_LANE)\n"
                "            self.fan_modes, self.ordered_fan_speeds = "
                "build_fan_speed_map(\n"
                "                fan_mode_names, lane\n"
                "            )\n"
            ),
            (
                "        if features & ClimateEntityFeature.FAN_MODE and "
                "fan_mode_names:\n"
                "            self.fan_modes, self.ordered_fan_speeds = "
                "build_fan_speed_map(\n"
                "                fan_mode_names\n"
                "            )\n"
            ),
        ),
    ],
    "climate_util.py": [
        (
            "fan_lane: drop FAN_HIGH/FAN_LOW/FAN_MEDIUM/FAN_MIDDLE climate imports",
            (
                "    DEFAULT_MIN_TEMP,\n"
                "    FAN_HIGH,\n"
                "    FAN_LOW,\n"
                "    FAN_MEDIUM,\n"
                "    FAN_MIDDLE,\n"
                "    FAN_OFF,\n"
            ),
            "    DEFAULT_MIN_TEMP,\n    FAN_OFF,\n",
        ),
        (
            "imports: drop absolute homekit.util import (re-added relative below)",
            (
                "from homeassistant.components.homekit.util import "
                "temperature_to_homekit\n"
                "from homeassistant.const import STATE_UNAVAILABLE, "
                "STATE_UNKNOWN\n"
            ),
            "from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN\n",
        ),
        (
            "imports: replace fan_lane .const import with relative .util import",
            "from .const import FAN_LANE_AUTO\n",
            "from .util import temperature_to_homekit\n",
        ),
        (
            "fan_lane: drop the FAN_MID and MANUAL_FAN_LANE constants",
            (
                'ORDERED_AUTO_FAN_SPEEDS = ["low/auto", "mid/auto", "high/auto"]\n'
                'FAN_MID = "mid"  # Common vendor alias between LOW and MIDDLE.\n'
                "MANUAL_FAN_LANE = [FAN_LOW, FAN_MID, FAN_MIDDLE, FAN_MEDIUM, "
                "FAN_HIGH]\n"
                "SWING_ON_SET = {SWING_ON, SWING_BOTH, SWING_HORIZONTAL, "
                "SWING_VERTICAL}\n"
            ),
            (
                'ORDERED_AUTO_FAN_SPEEDS = ["low/auto", "mid/auto", "high/auto"]\n'
                "SWING_ON_SET = {SWING_ON, SWING_BOTH, SWING_HORIZONTAL, "
                "SWING_VERTICAL}\n"
            ),
        ),
        (
            "fan_lane: drop the lane parameter and manual-lane branch in "
            "build_fan_speed_map",
            (
                "def build_fan_speed_map(\n"
                "    fan_modes: list[str], lane: str\n"
                ") -> tuple[dict[str, str], list[str]]:\n"
                '    """Return the lowercase to original fan map and ordered '
                'slider keys."""\n'
                "    modes = {mode.lower(): mode for mode in fan_modes}\n"
                "    lane_order = ORDERED_AUTO_FAN_SPEEDS if lane == "
                "FAN_LANE_AUTO else MANUAL_FAN_LANE\n"
                "    ordered = [mode for mode in lane_order if mode in modes]\n"
            ),
            (
                "def build_fan_speed_map(fan_modes: list[str]) -> "
                "tuple[dict[str, str], list[str]]:\n"
                '    """Return the lowercase to original fan map and ordered '
                'slider keys."""\n'
                "    modes = {mode.lower(): mode for mode in fan_modes}\n"
                "    ordered = [mode for mode in ORDERED_AUTO_FAN_SPEEDS if mode "
                "in modes]\n"
            ),
        ),
    ],
}


def project(name: str, source: str) -> str:
    """Return the core-layout projection of one shared file's source text."""
    result = source
    for description, old, new in TRANSFORMS[name]:
        count = result.count(old)
        if count != 1:
            raise SystemExit(
                f"port_to_core: transform '{description}' for {name} matched "
                f"{count} times (expected exactly 1). The custom-component source "
                f"has drifted from the shape this transform encodes; update "
                f"TRANSFORMS in scripts/port_to_core.py."
            )
        result = result.replace(old, new, 1)
    return result


def load_sources() -> dict[str, str]:
    """Read the CC's shared files from disk."""
    sources = {}
    for name in SHARED_FILES:
        path = CC_DIR / name
        try:
            sources[name] = path.read_text(encoding="utf-8")
        except OSError as err:
            raise SystemExit(f"port_to_core: cannot read source {path}: {err}") from err
    return sources


def cmd_out(out_dir: Path) -> int:
    """Write the projected files into out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, source in load_sources().items():
        target = out_dir / name
        target.write_text(project(name, source), encoding="utf-8")
        print(f"wrote {target}")
    return 0


def cmd_check(core_dir: Path) -> int:
    """Assert every projected file is byte-identical to its copy in core_dir."""
    ok = True
    for name, source in load_sources().items():
        projected = project(name, source)
        target = core_dir / name
        try:
            expected = target.read_text(encoding="utf-8")
        except OSError as err:
            print(
                f"port_to_core: cannot read core file {target}: {err}",
                file=sys.stderr,
            )
            ok = False
            continue
        if projected == expected:
            print(f"OK: {name} projection is byte-identical to {target}")
            continue
        ok = False
        print(
            f"MISMATCH: {name} projection differs from {target}",
            file=sys.stderr,
        )
        sys.stderr.writelines(
            difflib.unified_diff(
                projected.splitlines(keepends=True),
                expected.splitlines(keepends=True),
                fromfile=f"projected/{name}",
                tofile=str(target),
            )
        )
    if not ok:
        print(
            "\nport_to_core: projection does not match the core files. Either the "
            "CC and core have diverged beyond the documented delta, or the "
            "transform needs updating.",
            file=sys.stderr,
        )
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the requested mode."""
    parser = argparse.ArgumentParser(
        description="Project the CC's shared HomeKit files into core layout.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--out",
        metavar="DIR",
        type=Path,
        help="write the projected type_heatercooler.py and climate_util.py here",
    )
    group.add_argument(
        "--check",
        metavar="COREDIR",
        type=Path,
        help="assert the projection is byte-identical to the files in COREDIR",
    )
    args = parser.parse_args(argv)
    if args.out is not None:
        return cmd_out(args.out)
    return cmd_check(args.check)


if __name__ == "__main__":
    sys.exit(main())
