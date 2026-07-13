# HomeKit HeaterCooler Bridge for Home Assistant

[![HACS][hacs-badge]][hacs-url]
[![GitHub Release][release-badge]][release-url]
[![License][license-badge]][license-url]
[![Validate][validate-badge]][validate-url]

Expose selected Home Assistant `climate` entities as a native **HeaterCooler** accessory in Apple Home via HomeKit Bridge.

## Why this exists

Home Assistant's HomeKit Bridge maps `climate` entities to a Thermostat accessory. For air conditioners and heat pumps (for example, Daikin units), a native **HeaterCooler** tile is a better fit: one tile carries the mode, target temperature, cooling and heating thresholds, fan speed, and swing, with power as a separate control and an idle state once the room is at temperature.

[Native HeaterCooler support](https://github.com/home-assistant/core/pull/148231) is now merged into Home Assistant core `dev`. It was merged after Home Assistant 2026.7.2, so this integration remains the legacy implementation for that release and earlier versions.

Once Home Assistant includes native support, this integration routes the entities you select through core's native HeaterCooler class instead of replacing it. That keeps an existing configuration working while you migrate. In the HomeKit Bridge options, choose **Heater Cooler** for each selected climate entity, then remove this integration.

## Features

- Native HomeKit **HeaterCooler** service for selected climates
- Uses core's native implementation automatically when it is available
- Maps HVAC mode, active state, thresholds, fan speed, and swing mode
- Configurable fan slider mode on legacy cores
- Supports single setpoint and dual threshold climates
- Derives heating and cooling activity when an integration omits `hvac_action`
- Exposes reported current humidity through a linked HomeKit sensor
- Safe-by-default targeting (`include_entities` required)
- Adds a diagnostic sensor so you can verify active patch coverage in Home Assistant UI
- No changes to your live system needed until you install it

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant
2. Click **⋮ → Custom repositories**
3. Add `https://github.com/teh-hippo/ha-homekit-heatercooler` as an **Integration**
4. Install **HomeKit HeaterCooler Bridge**
5. Restart Home Assistant

### Manual

1. Copy `custom_components/homekit_heatercooler` to `<HA_CONFIG>/custom_components/`
2. Restart Home Assistant

## Configuration

No `configuration.yaml` changes are required.

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **HomeKit HeaterCooler Bridge**
3. Select one or more `climate` entities in **Include entities**
4. Optionally set **Exclude entities**
5. Choose the **Fan slider mode** (see below)
6. Save

You can change these later from **Settings → Devices & Services → HomeKit HeaterCooler Bridge → Configure**.

To confirm the override is active, open the integration device page and check the **Patched entities** diagnostic sensor.

### Fan slider mode

HomeKit's HeaterCooler tile has a single linear fan slider, so this integration maps it to three speeds. **Fan slider mode** chooses which of the entity's fan modes those three positions drive:

- **Auto** (default): the auto-referenced speeds when the entity exposes them (for example a Daikin's `Low/Auto`, `Mid/Auto`, `High/Auto`).
- **Manual**: the fixed speeds (for example `Low`, `Mid`, `High`).

If the entity has no fan modes matching the chosen mode, its own fan modes are used as-is. Fan modes outside the chosen mode stay available from the underlying `climate` entity.

This setting applies only to the legacy implementation. Core's native HeaterCooler keeps automatic fan control through a linked Fan service instead.

### Migrating to native HomeKit support

When your Home Assistant release includes native HeaterCooler support:

1. Open **Settings → Devices & Services → HomeKit Bridge → Configure**.
2. Choose **Heater Cooler** for each climate entity currently selected here.
3. Confirm the native accessory in Apple Home, then remove this integration.

## How this patch works

- You select one or more `climate` entities in this integration.
- On legacy cores, those entities use this integration's **HeaterCooler** implementation.
- On native cores, those entities use Home Assistant's built-in **HeaterCooler** implementation.
- Everything else in HomeKit keeps its normal behavior.
- Home Assistant core files are not changed on disk.

It keeps working across normal restarts while:

- `custom_components/homekit_heatercooler` is installed
- at least one target entity is configured in this integration
- the target entities are included in HomeKit Bridge

The diagnostic sensor reports whether the selected entities use the legacy or native route.

## Development (uv)

```bash
bash scripts/check.sh
```

Requires [uv](https://docs.astral.sh/uv/). Uses [Conventional Commits](https://www.conventionalcommits.org/).

### Hardware-free end-to-end smoke

[`tests/harness/configuration.yaml`](tests/harness/configuration.yaml) configures the reusable [HA test harness](https://github.com/teh-hippo/ha-test-harness): it routes `Mock Daikin` through this integration while keeping `Mock Dual Swing` as a Thermostat. The native-core workflow uses [`tests/harness/configuration-native.yaml`](tests/harness/configuration-native.yaml), which pins both entities to Thermostat first so the selective override is proven rather than hidden by core's automatic routing.

```bash
HARNESS_DIR=/path/to/ha-test-harness
"$HARNESS_DIR/podman/ha-bench.sh" --name heatercooler-harness --host-net \
  --component "$HARNESS_DIR/mocks/custom_components/mock_climate" \
  --component "$PWD/custom_components/homekit_heatercooler" \
  --seed-config "$PWD/tests/harness/configuration.yaml"
```

Use the harness’s [HomeKit smoke](https://github.com/teh-hippo/ha-test-harness/tree/master/homekit) to pair, assert the two accessory types, and unpair the disposable bridge. [`tests/harness/hap_write_smoke.py`](tests/harness/hap_write_smoke.py) verifies that a HAP target-mode write reaches Mock Daikin. The manual **HAP harness smoke** workflow checks both the legacy 2026.7.2 route and the native core `dev` route.

## License

[MIT](LICENSE)

[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs-url]: https://github.com/hacs/integration
[release-badge]: https://img.shields.io/github/v/release/teh-hippo/ha-homekit-heatercooler
[release-url]: https://github.com/teh-hippo/ha-homekit-heatercooler/releases
[license-badge]: https://img.shields.io/github/license/teh-hippo/ha-homekit-heatercooler
[license-url]: https://github.com/teh-hippo/ha-homekit-heatercooler/blob/master/LICENSE
[validate-badge]: https://img.shields.io/github/actions/workflow/status/teh-hippo/ha-homekit-heatercooler/validate.yml?branch=master&label=validate
[validate-url]: https://github.com/teh-hippo/ha-homekit-heatercooler/actions/workflows/validate.yml
