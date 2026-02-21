"""Constants for the HomeKit HeaterCooler patch integration."""

from homeassistant.const import Platform

DOMAIN = "homekit_heatercooler"
PLATFORMS: list[Platform] = [Platform.SENSOR]
DATA_PATCH_STATE = "patch_state"
DATA_PATCH_STATUS = "patch_status"
DATA_YAML_INCLUDE_ENTITIES = "yaml_include_entities"
DATA_YAML_EXCLUDE_ENTITIES = "yaml_exclude_entities"
SIGNAL_PATCH_STATUS_UPDATED = f"{DOMAIN}_patch_status_updated"
