# HomeKit HeaterCooler Bridge for Home Assistant

[![HACS][hacs-badge]][hacs-url]
[![GitHub Release][release-badge]][release-url]
[![License][license-badge]][license-url]
[![Validate][validate-badge]][validate-url]

Expose selected Home Assistant `climate` entities as a native **HeaterCooler** accessory in Apple Home via HomeKit Bridge.

This integration is inspired by Home Assistant core PR #148231:

- https://github.com/home-assistant/core/pull/148231

## Why this exists

On current core releases, HomeKit Bridge maps climate entities to Thermostat behavior. For Daikin-style units, this can be a worse UX than a native HeaterCooler tile.

This custom integration patches HomeKit mapping for explicitly included entities (for example, `climate.aircon`), while leaving all other entities untouched.

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

Add this to `configuration.yaml`:

```yaml
homekit_heatercooler:
  include_entities:
    - climate.aircon
```

Optional exclusions:

```yaml
homekit_heatercooler:
  include_entities:
    - climate.aircon
  exclude_entities:
    - climate.some_other_unit
```

## Migration notes

- HomeKit may show old thermostat/fan tiles from previous mapping.
- Remove stale tiles and assign the newly exposed HeaterCooler accessory to the desired room.
- Existing HomeKit automations/scenes tied to old tiles may need updates.

## How this patch works

This integration uses a runtime patch ("monkey patch") during Home Assistant startup:

- It replaces HomeKit accessory selection functions in memory for the running process.
- It only redirects explicitly included entities (for example `climate.aircon`) to `HeaterCooler`.
- It does **not** modify Home Assistant core files on disk.

In practice, this is a targeted runtime override inside a custom integration.

## Persistence and upgrade behavior

What persists:

- Reboots and normal Home Assistant restarts (patch reapplies on startup)
- HomeKit Bridge reloads

What can remove or break it:

- Removing `custom_components/homekit_heatercooler`
- Removing `homekit_heatercooler:` from `configuration.yaml`
- Removing the entity from HomeKit bridge `include_entities`
- Restores/rebuilds that overwrite `/config/custom_components` or config
- Home Assistant core updates that change HomeKit internals this patch hooks into

So yes: future Home Assistant/HomeKit Bridge core upgrades can break this patch, and the behavior can fall back to default HomeKit climate mapping.

## Official references

- Home Assistant developer docs: where integrations are loaded from (`custom_components` takes precedence)  
  https://developers.home-assistant.io/docs/creating_integration_file_structure/
- Home Assistant developer tips: testing core integration changes by copying into `/config/custom_components`, and reminder that this overrides core behavior until removed  
  https://developers.home-assistant.io/docs/development_tips/
- Home Assistant manifest requirements: custom integrations require a `version`  
  https://developers.home-assistant.io/docs/creating_integration_manifest/
- Home Assistant core changelogs (watch each upgrade for breaking changes)  
  https://www.home-assistant.io/changelogs/core-2026.2/
- Python `patch()` reference (official standard-library concept for runtime replacement in Python)  
  https://docs.python.org/3/library/unittest.mock.html#patch

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
