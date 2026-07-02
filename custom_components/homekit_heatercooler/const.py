"""Constants for the HomeKit HeaterCooler patch integration."""

from homeassistant.const import Platform

DOMAIN = "homekit_heatercooler"
PLATFORMS: list[Platform] = [Platform.SENSOR]
DATA_PATCH_STATE = "patch_state"
DATA_PATCH_STATUS = "patch_status"
DATA_PATCH_STATUS_UNSUB = "patch_status_unsub"
DATA_YAML_INCLUDE_ENTITIES = "yaml_include_entities"
DATA_YAML_EXCLUDE_ENTITIES = "yaml_exclude_entities"
DATA_YAML_FAN_LANE = "yaml_fan_lane"
SIGNAL_PATCH_STATUS_UPDATED = f"{DOMAIN}_patch_status_updated"

CONF_FAN_LANE = "fan_lane"
FAN_LANE_AUTO = "auto"
FAN_LANE_MANUAL = "manual"
DEFAULT_FAN_LANE = FAN_LANE_AUTO
