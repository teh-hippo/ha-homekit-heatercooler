"""HomeKit HeaterCooler accessory implementation for climate entities."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_HVAC_MODES,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_SWING_MODE,
    ATTR_SWING_MODES,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ATTR_TEMPERATURE,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_MIDDLE,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_SWING_MODE,
    SERVICE_SET_TEMPERATURE,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.climate import (
    DOMAIN as DOMAIN_CLIMATE,
)
from homeassistant.components.homekit import const as homekit_const
from homeassistant.components.homekit.accessories import TYPES, HomeAccessory
from homeassistant.components.homekit.util import temperature_to_homekit, temperature_to_states
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import State
from homeassistant.exceptions import ServiceNotFound, ServiceValidationError
from homeassistant.util.enum import try_parse_enum
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)
from pyhap.const import CATEGORY_THERMOSTAT

_LOGGER = logging.getLogger(__name__)

CHAR_ACTIVE = homekit_const.CHAR_ACTIVE
CHAR_COOLING_THRESHOLD_TEMPERATURE = homekit_const.CHAR_COOLING_THRESHOLD_TEMPERATURE
CHAR_CURRENT_TEMPERATURE = homekit_const.CHAR_CURRENT_TEMPERATURE
CHAR_HEATING_THRESHOLD_TEMPERATURE = homekit_const.CHAR_HEATING_THRESHOLD_TEMPERATURE
CHAR_ROTATION_SPEED = homekit_const.CHAR_ROTATION_SPEED
CHAR_SWING_MODE = homekit_const.CHAR_SWING_MODE
PROP_MAX_VALUE = homekit_const.PROP_MAX_VALUE
PROP_MIN_STEP = homekit_const.PROP_MIN_STEP
PROP_MIN_VALUE = homekit_const.PROP_MIN_VALUE
CHAR_CURRENT_HEATER_COOLER_STATE = getattr(
    homekit_const, "CHAR_CURRENT_HEATER_COOLER_STATE", "CurrentHeaterCoolerState"
)
CHAR_TARGET_HEATER_COOLER_STATE = getattr(homekit_const, "CHAR_TARGET_HEATER_COOLER_STATE", "TargetHeaterCoolerState")
SERV_HEATER_COOLER = getattr(homekit_const, "SERV_HEATER_COOLER", "HeaterCooler")

# HomeKit CurrentHeaterCoolerState values (per HomeKit spec)
HC_INACTIVE, HC_IDLE, HC_HEATING, HC_COOLING = range(4)
# HomeKit TargetHeaterCoolerState values
HC_TARGET_AUTO, HC_TARGET_HEAT, HC_TARGET_COOL = range(3)

HC_HASS_TO_HOMEKIT_TARGET = {
    HVACMode.OFF: HC_TARGET_AUTO,
    HVACMode.HEAT: HC_TARGET_HEAT,
    HVACMode.COOL: HC_TARGET_COOL,
    HVACMode.HEAT_COOL: HC_TARGET_AUTO,
    HVACMode.AUTO: HC_TARGET_AUTO,
}
HC_HOMEKIT_TO_HASS_TARGET_BASE = {
    HC_TARGET_HEAT: HVACMode.HEAT,
    HC_TARGET_COOL: HVACMode.COOL,
}
HC_HASS_TO_HOMEKIT_ACTION = {
    HVACAction.OFF: HC_INACTIVE,
    HVACAction.IDLE: HC_IDLE,
    HVACAction.HEATING: HC_HEATING,
    HVACAction.PREHEATING: HC_HEATING,
    HVACAction.COOLING: HC_COOLING,
    HVACAction.DRYING: HC_COOLING,
    HVACAction.FAN: HC_COOLING,
    HVACAction.DEFROSTING: HC_HEATING,
}
ORDERED_FAN_SPEEDS = [
    "auto",
    FAN_LOW,
    "low/auto",
    "mid",
    FAN_MIDDLE,
    "mid/auto",
    FAN_MEDIUM,
    FAN_HIGH,
    "high/auto",
]
SWING_ON_SET = {"on", "both", "horizontal", "vertical"}


def _as_float(value: Any) -> float | None:
    """Convert HomeKit characteristic values to float where possible."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _temp(state: State, key: str, unit: str) -> float | None:
    """Return a temperature attribute converted to HomeKit units."""
    value = state.attributes.get(key)
    if value is None:
        return None
    return float(temperature_to_homekit(value, unit))


class HeaterCooler(HomeAccessory):  # type: ignore[misc]
    """Expose a climate entity as a native HomeKit HeaterCooler."""

    def __init__(self, *args: Any) -> None:
        """Initialize a HeaterCooler accessory."""
        super().__init__(*args, category=CATEGORY_THERMOSTAT)
        self._unit = self.hass.config.units.temperature_unit

        state = self.hass.states.get(self.entity_id)
        assert state
        attributes = state.attributes
        features = attributes.get(ATTR_SUPPORTED_FEATURES, 0)

        hvac_modes = attributes.get(ATTR_HVAC_MODES, [])
        current_mode = try_parse_enum(HVACMode, state.state)

        supports_auto = HVACMode.AUTO in hvac_modes
        supports_heat_cool = HVACMode.HEAT_COOL in hvac_modes
        if current_mode == HVACMode.AUTO:
            supports_auto = True
        elif current_mode == HVACMode.HEAT_COOL:
            supports_heat_cool = True

        self._hk_to_ha_target = HC_HOMEKIT_TO_HASS_TARGET_BASE.copy()
        if supports_auto:
            self._hk_to_ha_target[HC_TARGET_AUTO] = HVACMode.AUTO
        elif supports_heat_cool:
            self._hk_to_ha_target[HC_TARGET_AUTO] = HVACMode.HEAT_COOL
        else:
            self._hk_to_ha_target[HC_TARGET_AUTO] = HVACMode.HEAT_COOL

        raw_step = attributes.get("temperature_step", 1)
        try:
            self._step = float(raw_step)
        except (TypeError, ValueError):
            self._step = 1.0

        chars = [
            CHAR_ACTIVE,
            CHAR_CURRENT_HEATER_COOLER_STATE,
            CHAR_TARGET_HEATER_COOLER_STATE,
            CHAR_CURRENT_TEMPERATURE,
            CHAR_COOLING_THRESHOLD_TEMPERATURE,
            CHAR_HEATING_THRESHOLD_TEMPERATURE,
        ]
        if features & ClimateEntityFeature.FAN_MODE:
            chars.append(CHAR_ROTATION_SPEED)
        if features & ClimateEntityFeature.SWING_MODE:
            chars.append(CHAR_SWING_MODE)

        service = self.add_preload_service(SERV_HEATER_COOLER, chars)
        self.set_primary_service(service)

        self.char_active = service.configure_char(CHAR_ACTIVE, value=0)
        self.char_current_state = service.configure_char(CHAR_CURRENT_HEATER_COOLER_STATE, value=HC_INACTIVE)
        self.char_target_state = service.configure_char(CHAR_TARGET_HEATER_COOLER_STATE, value=HC_TARGET_AUTO)
        self.char_current_temp = service.configure_char(CHAR_CURRENT_TEMPERATURE, value=21.0)

        min_temp_c = attributes.get(ATTR_MIN_TEMP, 7.0)
        max_temp_c = attributes.get(ATTR_MAX_TEMP, 35.0)
        min_temp_hk = temperature_to_homekit(min_temp_c, self._unit)
        max_temp_hk = temperature_to_homekit(max_temp_c, self._unit)

        step_hk = self._step
        if self._unit != "°C":
            step_hk = self._step * 5.0 / 9.0

        temp_properties = {
            PROP_MIN_VALUE: min_temp_hk,
            PROP_MAX_VALUE: max_temp_hk,
            PROP_MIN_STEP: step_hk,
        }
        self.char_cool = service.configure_char(
            CHAR_COOLING_THRESHOLD_TEMPERATURE,
            value=24.0,
            properties=temp_properties,
        )
        self.char_heat = service.configure_char(
            CHAR_HEATING_THRESHOLD_TEMPERATURE,
            value=24.0,
            properties=temp_properties,
        )

        self.ordered_fan_speeds: list[str] = []
        if features & ClimateEntityFeature.FAN_MODE and (modes := attributes.get(ATTR_FAN_MODES)):
            self.fan_modes = {mode.lower(): mode for mode in modes}
            ordered_modes = [mode for mode in ORDERED_FAN_SPEEDS if mode in self.fan_modes]
            self.ordered_fan_speeds = ordered_modes or list(self.fan_modes.keys())
            self.char_speed = service.configure_char(
                CHAR_ROTATION_SPEED,
                value=100,
                properties={PROP_MIN_STEP: 100 / len(self.ordered_fan_speeds)},
            )

        if features & ClimateEntityFeature.SWING_MODE and (swing_modes := attributes.get(ATTR_SWING_MODES)):
            self.swing_on_mode = next(
                (mode for mode in swing_modes if mode.lower() in SWING_ON_SET),
                swing_modes[0],
            )
            self.char_swing = service.configure_char(CHAR_SWING_MODE, value=0)

        self._last_known_mode = current_mode or HVACMode.COOL
        self.async_update_state(state)
        service.setter_callback = self._set_chars

    def _set_chars(self, char_values: dict[str, Any]) -> None:
        """Handle writes to multiple HeaterCooler characteristics at once."""
        service_calls: list[tuple[str, dict[str, Any]]] = []
        self._handle_active_mode_changes(char_values, service_calls)
        self._handle_temperature_changes(char_values, service_calls)
        self._handle_fan_swing_changes(char_values)

        for service_name, service_data in service_calls:
            try:
                self.async_call_service(
                    DOMAIN_CLIMATE,
                    service_name,
                    {ATTR_ENTITY_ID: self.entity_id, **service_data},
                )
            except (ServiceNotFound, ServiceValidationError) as err:
                _LOGGER.error("Failed to execute %s for %s: %s", service_name, self.entity_id, err)

    def _handle_active_mode_changes(
        self,
        char_values: dict[str, Any],
        service_calls: list[tuple[str, dict[str, Any]]],
    ) -> None:
        """Handle Active and TargetHeaterCoolerState writes."""
        active = char_values.get(CHAR_ACTIVE)
        target_mode = char_values.get(CHAR_TARGET_HEATER_COOLER_STATE)

        current_state = self.hass.states.get(self.entity_id)
        currently_active = current_state and current_state.state not in (
            HVACMode.OFF,
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        )

        if active is None and target_mode is None:
            return

        if active == 0:
            service_calls.append(("turn_off", {}))
            return

        target_mode_int = None
        if target_mode is not None:
            try:
                target_mode_int = int(target_mode)
            except (TypeError, ValueError):
                target_mode_int = None

        if target_mode_int is not None:
            hass_mode = self._hk_to_ha_target.get(target_mode_int)
            if hass_mode:
                service_calls.append((SERVICE_SET_HVAC_MODE, {ATTR_HVAC_MODE: hass_mode}))
                self._last_known_mode = hass_mode
            return

        if active == 1 and not currently_active:
            service_calls.append((SERVICE_SET_HVAC_MODE, {ATTR_HVAC_MODE: self._last_known_mode}))

    def _handle_temperature_changes(
        self,
        char_values: dict[str, Any],
        service_calls: list[tuple[str, dict[str, Any]]],
    ) -> None:
        """Handle cooling/heating threshold writes."""
        cooling_temp = _as_float(char_values.get(CHAR_COOLING_THRESHOLD_TEMPERATURE))
        heating_temp = _as_float(char_values.get(CHAR_HEATING_THRESHOLD_TEMPERATURE))
        if cooling_temp is None and heating_temp is None:
            return

        current_state = self.hass.states.get(self.entity_id)
        supports_dual_temp = current_state and (
            ATTR_TARGET_TEMP_HIGH in current_state.attributes or ATTR_TARGET_TEMP_LOW in current_state.attributes
        )

        if supports_dual_temp:
            temp_data: dict[str, float] = {}
            if cooling_temp is not None:
                temp_data[ATTR_TARGET_TEMP_HIGH] = temperature_to_states(cooling_temp, self._unit)
            if heating_temp is not None:
                temp_data[ATTR_TARGET_TEMP_LOW] = temperature_to_states(heating_temp, self._unit)
            if temp_data:
                service_calls.append((SERVICE_SET_TEMPERATURE, temp_data))
            return

        self._handle_single_temp_changes(service_calls, cooling_temp, heating_temp)

    def _handle_single_temp_changes(
        self,
        service_calls: list[tuple[str, dict[str, Any]]],
        cooling_temp: float | None,
        heating_temp: float | None,
    ) -> None:
        """Handle temperature writes for single-setpoint entities."""
        current_state = self.hass.states.get(self.entity_id)
        if not current_state:
            return

        selected_temp: float | None = None
        current_mode = current_state.state
        if current_mode == HVACMode.COOL and cooling_temp is not None:
            selected_temp = cooling_temp
        elif current_mode == HVACMode.HEAT and heating_temp is not None:
            selected_temp = heating_temp
        elif current_mode == HVACMode.HEAT_COOL:
            if cooling_temp is not None and heating_temp is not None:
                current_target = current_state.attributes.get(ATTR_TEMPERATURE)
                if current_target and abs(cooling_temp - current_target) > abs(heating_temp - current_target):
                    selected_temp = cooling_temp
                else:
                    selected_temp = heating_temp
            elif cooling_temp is not None:
                selected_temp = cooling_temp
            elif heating_temp is not None:
                selected_temp = heating_temp
        elif cooling_temp is not None:
            selected_temp = cooling_temp
        elif heating_temp is not None:
            selected_temp = heating_temp

        if selected_temp is None:
            return

        service_calls.append(
            (
                SERVICE_SET_TEMPERATURE,
                {ATTR_TEMPERATURE: temperature_to_states(selected_temp, self._unit)},
            )
        )

    def _handle_fan_swing_changes(self, char_values: dict[str, Any]) -> None:
        """Handle fan speed and swing mode writes."""
        if CHAR_ROTATION_SPEED in char_values:
            self._set_fan_speed(char_values[CHAR_ROTATION_SPEED])
        if CHAR_SWING_MODE in char_values:
            self._set_swing_mode(char_values[CHAR_SWING_MODE])

    def _set_fan_speed(self, speed: Any) -> None:
        """Set fan speed through the climate service."""
        if not self.ordered_fan_speeds:
            return

        speed_value = _as_float(speed)
        if speed_value is None or speed_value <= 0 or speed_value > 100:
            return

        fan_mode = percentage_to_ordered_list_item(self.ordered_fan_speeds, speed_value)
        fan_mode = self.fan_modes.get(fan_mode, fan_mode)
        try:
            self.async_call_service(
                DOMAIN_CLIMATE,
                SERVICE_SET_FAN_MODE,
                {ATTR_ENTITY_ID: self.entity_id, ATTR_FAN_MODE: fan_mode},
            )
        except (ServiceNotFound, ServiceValidationError) as err:
            _LOGGER.error("Failed to set fan mode for %s: %s", self.entity_id, err)

    def _set_swing_mode(self, swing_on: Any) -> None:
        """Set swing mode through the climate service."""
        if not hasattr(self, "swing_on_mode"):
            return

        state = self.hass.states.get(self.entity_id)
        if not state:
            return

        swing_modes = state.attributes.get(ATTR_SWING_MODES, [])
        current_swing = state.attributes.get(ATTR_SWING_MODE)
        swing_enabled = bool(int(_as_float(swing_on) or 0))

        if swing_enabled:
            target_mode = self.swing_on_mode
        else:
            off_modes = {"off", "false", "0"}
            target_mode = next(
                (mode for mode in swing_modes if mode.lower() in off_modes),
                swing_modes[0] if swing_modes else "off",
            )

        if target_mode == current_swing:
            return

        try:
            self.async_call_service(
                DOMAIN_CLIMATE,
                SERVICE_SET_SWING_MODE,
                {ATTR_ENTITY_ID: self.entity_id, ATTR_SWING_MODE: target_mode},
            )
        except (ServiceNotFound, ServiceValidationError) as err:
            _LOGGER.error("Failed to set swing mode for %s: %s", self.entity_id, err)

    def _hk_target_mode(self, state: State) -> int | None:
        """Map Home Assistant hvac_mode to HomeKit target mode."""
        if state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return None
        mode = try_parse_enum(HVACMode, state.state)
        if not mode:
            return None

        hk_value = HC_HASS_TO_HOMEKIT_TARGET.get(mode)
        if hk_value is not None and hk_value in self._hk_to_ha_target:
            return hk_value
        return None

    def async_update_state(self, new_state: State) -> None:
        """Update HomeKit characteristics from Home Assistant state."""
        attributes = new_state.attributes
        features = attributes.get(ATTR_SUPPORTED_FEATURES, 0)

        current_mode = try_parse_enum(HVACMode, new_state.state)
        if current_mode and current_mode != HVACMode.OFF:
            self._last_known_mode = current_mode

        if (target_mode := self._hk_target_mode(new_state)) is not None:
            self.char_target_state.set_value(target_mode)

        action = attributes.get(ATTR_HVAC_ACTION) or self._derive_action(new_state)
        self.char_current_state.set_value(HC_HASS_TO_HOMEKIT_ACTION.get(action, HC_INACTIVE))
        self.char_active.set_value(int(new_state.state not in (HVACMode.OFF, STATE_UNAVAILABLE, STATE_UNKNOWN)))

        if (current_temp := _temp(new_state, ATTR_CURRENT_TEMPERATURE, self._unit)) is not None:
            self.char_current_temp.set_value(current_temp)

        self._update_temperature_thresholds(new_state)

        if features & (ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.SWING_MODE):
            self._async_update_fan_state(new_state)

    def _update_temperature_thresholds(self, state: State) -> None:
        """Update cooling and heating threshold characteristics."""
        attributes = state.attributes
        supports_dual_temp = ATTR_TARGET_TEMP_HIGH in attributes or ATTR_TARGET_TEMP_LOW in attributes

        if supports_dual_temp:
            if (high_temp := _temp(state, ATTR_TARGET_TEMP_HIGH, self._unit)) is not None:
                self.char_cool.set_value(high_temp)
            if (low_temp := _temp(state, ATTR_TARGET_TEMP_LOW, self._unit)) is not None:
                self.char_heat.set_value(low_temp)
            return

        if (target_temp := _temp(state, ATTR_TEMPERATURE, self._unit)) is not None:
            self.char_cool.set_value(target_temp)
            self.char_heat.set_value(target_temp)

    def _async_update_fan_state(self, new_state: State) -> None:
        """Update fan speed and swing characteristics from entity state."""
        attributes = new_state.attributes
        if self.ordered_fan_speeds and hasattr(self, "char_speed"):
            current_fan_mode = attributes.get(ATTR_FAN_MODE)
            if current_fan_mode and current_fan_mode in self.fan_modes.values():
                for ordered_mode in self.ordered_fan_speeds:
                    if self.fan_modes.get(ordered_mode) == current_fan_mode:
                        self.char_speed.set_value(
                            ordered_list_item_to_percentage(self.ordered_fan_speeds, ordered_mode)
                        )
                        break

        if hasattr(self, "char_swing"):
            current_swing = str(attributes.get(ATTR_SWING_MODE, "")).lower()
            self.char_swing.set_value(1 if current_swing in SWING_ON_SET else 0)

    def _derive_action(self, state: State) -> HVACAction:
        """Derive hvac_action when an integration does not provide it."""
        mode = try_parse_enum(HVACMode, state.state)
        target = (
            state.attributes.get(ATTR_TEMPERATURE)
            or state.attributes.get(ATTR_TARGET_TEMP_HIGH)
            or state.attributes.get(ATTR_TARGET_TEMP_LOW)
        )
        current = state.attributes.get(ATTR_CURRENT_TEMPERATURE)
        if current is None or target is None or mode is None:
            return HVACAction.IDLE

        delta = 0.25
        if mode == HVACMode.COOL:
            return HVACAction.COOLING if current > target + delta else HVACAction.IDLE
        if mode == HVACMode.HEAT:
            return HVACAction.HEATING if current < target - delta else HVACAction.IDLE
        if mode in (HVACMode.HEAT_COOL, HVACMode.AUTO):
            if current > target + delta:
                return HVACAction.COOLING
            if current < target - delta:
                return HVACAction.HEATING
        return HVACAction.IDLE


def register_heatercooler_type() -> None:
    """Register HeaterCooler with HomeKit accessory registry if absent."""
    if "HeaterCooler" not in TYPES:
        TYPES.register("HeaterCooler")(HeaterCooler)
