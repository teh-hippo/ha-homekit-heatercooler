# HomeKit HeaterCooler Bridge for Home Assistant

[![HACS][hacs-badge]][hacs-url]
[![GitHub Release][release-badge]][release-url]
[![License][license-badge]][license-url]
[![Validate][validate-badge]][validate-url]

Expose selected Home Assistant `climate` entities as a native **HeaterCooler** accessory in Apple Home via HomeKit Bridge.

## Why this exists

On current core releases, HomeKit Bridge maps climate entities to Thermostat behavior. For Daikin-style units, this can be a worse UX than a native HeaterCooler tile.

This custom integration changes HomeKit mapping for explicitly included entities (for example, `climate.aircon`), while leaving all other entities untouched.

## Features

- Native HomeKit **HeaterCooler** service for selected climates
- Maps HVAC mode, active state, thresholds, fan speed, and swing mode
- Supports single setpoint and dual threshold climates
- Safe-by-default targeting (`include_entities` required)
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
5. Save

You can change these later from **Settings → Devices & Services → HomeKit HeaterCooler Bridge → Configure**.

## How this patch works

- Only entities listed in `include_entities` are affected.
- Those entities are shown in Apple Home as **HeaterCooler** instead of Thermostat.
- All other HomeKit entities keep their normal behavior.
- Home Assistant core files are not modified on disk.

This remains active across normal restarts as long as:

- `custom_components/homekit_heatercooler` is installed
- one or more target entities are configured in this integration
- your target entities are still included in HomeKit Bridge

After some Home Assistant updates, HomeKit internals may change. If that happens, entities can fall back to default mapping until this integration is updated.

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
