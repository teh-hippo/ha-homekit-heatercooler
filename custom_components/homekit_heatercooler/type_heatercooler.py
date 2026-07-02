"""HomeKit HeaterCooler accessory implementation for climate entities."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODES,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_SWING_MODE,
    ATTR_SWING_MODES,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ATTR_TARGET_TEMP_STEP,
    ATTR_TEMPERATURE,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_SWING_MODE,
    SERVICE_SET_TEMPERATURE,
    ClimateEntityFeature,
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
from homeassistant.util.enum import try_parse_enum
from pyhap.const import CATEGORY_THERMOSTAT

from .climate_util import (
    HC_INACTIVE,
    HC_TARGET_AUTO,
    as_float,
    build_fan_speed_map,
    build_target_state_map,
    current_heater_cooler_state,
    fan_mode_for_percentage,
    hk_target_mode,
    hk_temperature,
    is_active,
    percentage_for_fan_mode,
    plan_active_mode_change,
    resolve_swing_mode,
    select_single_setpoint,
    swing_is_on,
    target_state_valid_values,
)
from .const import CONF_FAN_LANE, DEFAULT_FAN_LANE

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


class HeaterCooler(HomeAccessory):
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

        self._hk_to_ha_target = build_target_state_map(supports_auto, supports_heat_cool)

        raw_step = attributes.get(ATTR_TARGET_TEMP_STEP, 1)
        self._step = float(raw_step) if isinstance(raw_step, (int, float)) else 1.0

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
        target_valid_values = target_state_valid_values(self._hk_to_ha_target)
        initial_target = (
            HC_TARGET_AUTO if HC_TARGET_AUTO in self._hk_to_ha_target else min(target_valid_values.values())
        )
        self.char_target_state = service.configure_char(
            CHAR_TARGET_HEATER_COOLER_STATE,
            value=initial_target,
            valid_values=target_valid_values,
        )
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
            lane = self.config.get(CONF_FAN_LANE, DEFAULT_FAN_LANE)
            self.fan_modes, self.ordered_fan_speeds = build_fan_speed_map(modes, lane)
            self.char_speed = service.configure_char(
                CHAR_ROTATION_SPEED,
                value=100,
                properties={PROP_MIN_STEP: 100 / len(self.ordered_fan_speeds)},
            )

        if features & ClimateEntityFeature.SWING_MODE and (swing_modes := attributes.get(ATTR_SWING_MODES)):
            self.swing_on_mode = next(
                (mode for mode in swing_modes if swing_is_on(mode)),
                swing_modes[0],
            )
            self.char_swing = service.configure_char(CHAR_SWING_MODE, value=0)

        self._last_known_mode: HVACMode = (
            current_mode if current_mode and current_mode != HVACMode.OFF else HVACMode.COOL
        )
        self.async_update_state(state)
        service.setter_callback = self._set_chars

    def _set_chars(self, char_values: dict[str, Any]) -> None:
        """Handle writes to multiple HeaterCooler characteristics at once."""
        service_calls: list[tuple[str, dict[str, Any]]] = []
        self._handle_active_mode_changes(char_values, service_calls)
        self._handle_temperature_changes(char_values, service_calls)
        self._handle_fan_swing_changes(char_values)

        for service_name, service_data in service_calls:
            self.async_call_service(
                DOMAIN_CLIMATE,
                service_name,
                {ATTR_ENTITY_ID: self.entity_id, **service_data},
            )

    def _handle_active_mode_changes(
        self,
        char_values: dict[str, Any],
        service_calls: list[tuple[str, dict[str, Any]]],
    ) -> None:
        """Handle Active and TargetHeaterCoolerState writes."""
        current_state = self.hass.states.get(self.entity_id)
        currently_active = bool(
            current_state and current_state.state not in (HVACMode.OFF, STATE_UNAVAILABLE, STATE_UNKNOWN)
        )
        calls, self._last_known_mode = plan_active_mode_change(
            char_values.get(CHAR_ACTIVE),
            char_values.get(CHAR_TARGET_HEATER_COOLER_STATE),
            currently_active,
            self._hk_to_ha_target,
            self._last_known_mode,
        )
        service_calls.extend(calls)

    def _handle_temperature_changes(
        self,
        char_values: dict[str, Any],
        service_calls: list[tuple[str, dict[str, Any]]],
    ) -> None:
        """Handle cooling/heating threshold writes."""
        cooling_temp = as_float(char_values.get(CHAR_COOLING_THRESHOLD_TEMPERATURE))
        heating_temp = as_float(char_values.get(CHAR_HEATING_THRESHOLD_TEMPERATURE))
        if cooling_temp is None and heating_temp is None:
            return

        current_state = self.hass.states.get(self.entity_id)
        if not current_state:
            return
        attributes = current_state.attributes

        if ATTR_TARGET_TEMP_HIGH in attributes or ATTR_TARGET_TEMP_LOW in attributes:
            temp_data: dict[str, float] = {}
            if cooling_temp is not None:
                temp_data[ATTR_TARGET_TEMP_HIGH] = temperature_to_states(cooling_temp, self._unit)
            if heating_temp is not None:
                temp_data[ATTR_TARGET_TEMP_LOW] = temperature_to_states(heating_temp, self._unit)
            if temp_data:
                service_calls.append((SERVICE_SET_TEMPERATURE, temp_data))
            return

        selected_temp = select_single_setpoint(
            current_state.state, cooling_temp, heating_temp, attributes.get(ATTR_TEMPERATURE)
        )
        if selected_temp is None:
            return
        service_calls.append(
            (SERVICE_SET_TEMPERATURE, {ATTR_TEMPERATURE: temperature_to_states(selected_temp, self._unit)})
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
        fan_mode = fan_mode_for_percentage(self.ordered_fan_speeds, self.fan_modes, speed)
        if fan_mode is None:
            return
        _LOGGER.debug("HeaterCooler %s fan speed %.2f%% -> %s", self.entity_id, float(speed), fan_mode)
        self.async_call_service(
            DOMAIN_CLIMATE,
            SERVICE_SET_FAN_MODE,
            {ATTR_ENTITY_ID: self.entity_id, ATTR_FAN_MODE: fan_mode},
        )

    def _set_swing_mode(self, swing_on: Any) -> None:
        """Set swing mode through the climate service."""
        if not hasattr(self, "swing_on_mode"):
            return

        state = self.hass.states.get(self.entity_id)
        if not state:
            return

        swing_modes = state.attributes.get(ATTR_SWING_MODES, [])
        current_swing = state.attributes.get(ATTR_SWING_MODE)
        swing_enabled = bool(int(as_float(swing_on) or 0))
        target_mode = resolve_swing_mode(swing_enabled, swing_modes, self.swing_on_mode)

        if target_mode == current_swing:
            return

        self.async_call_service(
            DOMAIN_CLIMATE,
            SERVICE_SET_SWING_MODE,
            {ATTR_ENTITY_ID: self.entity_id, ATTR_SWING_MODE: target_mode},
        )

    def async_update_state(self, new_state: State) -> None:
        """Update HomeKit characteristics from Home Assistant state."""
        attributes = new_state.attributes
        features = attributes.get(ATTR_SUPPORTED_FEATURES, 0)

        current_mode = try_parse_enum(HVACMode, new_state.state)
        if current_mode and current_mode != HVACMode.OFF:
            self._last_known_mode = current_mode

        if (target_mode := hk_target_mode(new_state.state, self._hk_to_ha_target)) is not None:
            self.char_target_state.set_value(target_mode)

        self.char_current_state.set_value(
            current_heater_cooler_state(new_state.state, attributes.get(ATTR_HVAC_ACTION))
        )
        self.char_active.set_value(is_active(new_state.state))

        if (current_temp := hk_temperature(attributes, ATTR_CURRENT_TEMPERATURE, self._unit)) is not None:
            self.char_current_temp.set_value(current_temp)

        self._update_temperature_thresholds(new_state)

        if features & (ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.SWING_MODE):
            self._async_update_fan_state(new_state)

    def _update_temperature_thresholds(self, state: State) -> None:
        """Update cooling and heating threshold characteristics."""
        attributes = state.attributes

        if ATTR_TARGET_TEMP_HIGH in attributes or ATTR_TARGET_TEMP_LOW in attributes:
            if (high_temp := hk_temperature(attributes, ATTR_TARGET_TEMP_HIGH, self._unit)) is not None:
                self.char_cool.set_value(high_temp)
            if (low_temp := hk_temperature(attributes, ATTR_TARGET_TEMP_LOW, self._unit)) is not None:
                self.char_heat.set_value(low_temp)
            return

        if (target_temp := hk_temperature(attributes, ATTR_TEMPERATURE, self._unit)) is not None:
            self.char_cool.set_value(target_temp)
            self.char_heat.set_value(target_temp)

    def _async_update_fan_state(self, new_state: State) -> None:
        """Update fan speed and swing characteristics from entity state."""
        attributes = new_state.attributes
        if self.ordered_fan_speeds and hasattr(self, "char_speed"):
            percentage = percentage_for_fan_mode(self.ordered_fan_speeds, self.fan_modes, attributes.get(ATTR_FAN_MODE))
            if percentage is not None:
                self.char_speed.set_value(percentage)

        if hasattr(self, "char_swing"):
            self.char_swing.set_value(1 if swing_is_on(attributes.get(ATTR_SWING_MODE)) else 0)


def register_heatercooler_type() -> None:
    """Register HeaterCooler with HomeKit accessory registry if absent."""
    if "HeaterCooler" not in TYPES:
        TYPES.register("HeaterCooler")(HeaterCooler)
