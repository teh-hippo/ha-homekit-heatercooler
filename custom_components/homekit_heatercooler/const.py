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
DATA_YAML_FAN_ENTITIES = "yaml_fan_entities"
SIGNAL_PATCH_STATUS_UPDATED = f"{DOMAIN}_patch_status_updated"

CONF_FAN_LANE = "fan_lane"
FAN_LANE_AUTO = "auto"
FAN_LANE_MANUAL = "manual"
DEFAULT_FAN_LANE = FAN_LANE_AUTO
TYPE_HEATER_COOLER = "heater_cooler"

# Maps a climate entity_id to a `fan` domain entity_id whose own percentage
# drives RotationSpeed instead of the climate entity's fan_modes attribute.
# Stored top-level, across YAML and every config entry, keyed by climate
# entity_id.
CONF_FAN_ENTITIES = "fan_entities"
# Per-accessory config key threaded from the resolved fan_entities mapping
# down to a single HeaterCooler instance (see patcher.py).
CONF_FAN_ENTITY_ID = "fan_entity_id"

# Released Home Assistant versions without native support do not expose these
# HeaterCooler characteristic and service names.
CHAR_ACTIVE = "Active"
CHAR_COOLING_THRESHOLD_TEMPERATURE = "CoolingThresholdTemperature"
CHAR_CURRENT_HEATER_COOLER_STATE = "CurrentHeaterCoolerState"
CHAR_CURRENT_HUMIDITY = "CurrentRelativeHumidity"
CHAR_CURRENT_TEMPERATURE = "CurrentTemperature"
CHAR_HEATING_THRESHOLD_TEMPERATURE = "HeatingThresholdTemperature"
CHAR_NAME = "Name"
CHAR_ROTATION_SPEED = "RotationSpeed"
CHAR_SWING_MODE = "SwingMode"
CHAR_TARGET_HEATER_COOLER_STATE = "TargetHeaterCoolerState"
PROP_MAX_VALUE = "maxValue"
PROP_MIN_STEP = "minStep"
PROP_MIN_VALUE = "minValue"
SERV_HEATER_COOLER = "HeaterCooler"
SERV_HUMIDITY_SENSOR = "HumiditySensor"
