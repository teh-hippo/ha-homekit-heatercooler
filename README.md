# HomeKit HeaterCooler Bridge for Home Assistant

[![HACS][hacs-badge]][hacs-url]
[![GitHub Release][release-badge]][release-url]
[![License][license-badge]][license-url]
[![Validate][validate-badge]][validate-url]

Expose selected Home Assistant `climate` entities as a native **HeaterCooler** accessory in Apple Home via HomeKit Bridge.

## Why this exists

Home Assistant's HomeKit Bridge maps `climate` entities to a Thermostat accessory. For air conditioners and heat pumps (for example, Daikin units), a native **HeaterCooler** tile is a better fit: one tile carries the mode, target temperature, cooling and heating thresholds, fan speed, and swing, with power as a separate control and an idle state once the room is at temperature.

Native HeaterCooler support was proposed for core in [home-assistant/core#148231](https://github.com/home-assistant/core/pull/148231) but was not accepted, so the Thermostat stays core's default. This integration provides the HeaterCooler mapping as an opt-in on top of the existing HomeKit Bridge, remapping only the `climate` entities you explicitly include (for example, `climate.aircon`). Everything else stays untouched.

## Features

- Native HomeKit **HeaterCooler** service for selected climates
- Maps HVAC mode, active state, thresholds, fan speed, and swing mode
- Supports single setpoint and dual threshold climates
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

## How this patch works

- You select one or more `climate` entities in this integration.
- Those entities appear in Apple Home as **HeaterCooler** instead of Thermostat.
- Everything else in HomeKit keeps its normal behavior.
- Home Assistant core files are not changed on disk.

It keeps working across normal restarts while:

- `custom_components/homekit_heatercooler` is installed
- at least one target entity is configured in this integration
- the target entities are included in HomeKit Bridge

After some Home Assistant updates, mapping can fall back to default behavior until this integration is updated.

## Development (uv)

```bash
bash scripts/check.sh
```

Requires [uv](https://docs.astral.sh/uv/). Uses [Conventional Commits](https://www.conventionalcommits.org/).

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
