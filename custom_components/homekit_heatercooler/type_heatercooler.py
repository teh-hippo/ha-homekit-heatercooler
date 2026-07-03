"""HomeKit HeaterCooler accessory implementation for climate entities."""

from __future__ import annotations

import logging
from collections.abc import Iterable
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
    ATTR_TARGET_TEMP_STEP,
    ATTR_TEMPERATURE,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_SWING_MODE,
    SERVICE_SET_TEMPERATURE,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.components.homekit import const as homekit_const
from homeassistant.components.homekit.accessories import TYPES, HomeAccessory
from homeassistant.components.homekit.util import temperature_to_states
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import State, callback
from homeassistant.util.enum import try_parse_enum
from pyhap.characteristic import Characteristic
from pyhap.const import CATEGORY_THERMOSTAT

from .climate_util import (
    HC_INACTIVE,
    HK_MAX_ROTATION_SPEED,
    _initial_last_known_mode,
    as_float,
    as_hap_integer,
    build_fan_speed_map,
    build_target_state_map,
    current_heater_cooler_state,
    fan_mode_for_percentage,
    hk_target_mode,
    hk_temperature,
    is_active,
    percentage_for_fan_mode,
    plan_active_mode_change,
    resolve_dual_setpoints,
    resolve_swing_mode,
    select_single_setpoint,
    swing_is_enabled,
    swing_is_off,
    swing_is_on,
    target_state_valid_values,
    temperature_range,
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


def _supported_hvac_modes(hvac_modes: Iterable[Any]) -> set[HVACMode]:
    """Return the declared Home Assistant HVAC modes as parsed enums."""
    supported_modes: set[HVACMode] = set()
    for raw_mode in hvac_modes:
        if mode := try_parse_enum(HVACMode, raw_mode):
            supported_modes.add(mode)
    return supported_modes


class HeaterCooler(HomeAccessory):
    """Expose a climate entity as a native HomeKit HeaterCooler."""

    def __init__(self, *args: Any) -> None:
        """Initialize a HeaterCooler accessory."""
        super().__init__(*args, category=CATEGORY_THERMOSTAT)
        self._reload_on_change_attrs.extend(
            (
                ATTR_HVAC_MODES,
                ATTR_FAN_MODES,
                ATTR_SWING_MODES,
                ATTR_MIN_TEMP,
                ATTR_MAX_TEMP,
            )
        )
        self._unit = self.hass.config.units.temperature_unit

        state = self.hass.states.get(self.entity_id)
        assert state
        attributes = state.attributes
        features = attributes.get(ATTR_SUPPORTED_FEATURES, 0)

        hvac_modes = attributes.get(ATTR_HVAC_MODES) or []
        current_mode = try_parse_enum(HVACMode, state.state)
        self._last_known_mode = _initial_last_known_mode(current_mode, hvac_modes)

        supports_auto = HVACMode.AUTO in hvac_modes
        supports_heat_cool = HVACMode.HEAT_COOL in hvac_modes
        supports_heat = HVACMode.HEAT in hvac_modes
        supports_cool = HVACMode.COOL in hvac_modes
        if current_mode == HVACMode.AUTO:
            supports_auto = True
        elif current_mode == HVACMode.HEAT_COOL:
            supports_heat_cool = True
        elif current_mode == HVACMode.HEAT:
            supports_heat = True
        elif current_mode == HVACMode.COOL:
            supports_cool = True

        self._hk_to_ha_target = build_target_state_map(supports_auto, supports_heat_cool, supports_heat, supports_cool)

        raw_step = attributes.get(ATTR_TARGET_TEMP_STEP, 1)
        self._step = float(raw_step) if isinstance(raw_step, (int, float)) else 1.0

        fan_mode_names = attributes.get(ATTR_FAN_MODES)
        swing_mode_names = attributes.get(ATTR_SWING_MODES)
        self.fan_modes: dict[str, str] = {}
        self.ordered_fan_speeds: list[str] = []
        if features & ClimateEntityFeature.FAN_MODE and fan_mode_names:
            lane = self.config.get(CONF_FAN_LANE, DEFAULT_FAN_LANE)
            self.fan_modes, self.ordered_fan_speeds = build_fan_speed_map(fan_mode_names, lane)

        chars = [
            CHAR_ACTIVE,
            CHAR_CURRENT_HEATER_COOLER_STATE,
            CHAR_TARGET_HEATER_COOLER_STATE,
            CHAR_CURRENT_TEMPERATURE,
            CHAR_COOLING_THRESHOLD_TEMPERATURE,
            CHAR_HEATING_THRESHOLD_TEMPERATURE,
        ]
        if self.ordered_fan_speeds:
            chars.append(CHAR_ROTATION_SPEED)
        if features & ClimateEntityFeature.SWING_MODE and swing_mode_names:
            chars.append(CHAR_SWING_MODE)

        service = self.add_preload_service(SERV_HEATER_COOLER, chars)
        self.set_primary_service(service)

        self.char_active = service.configure_char(CHAR_ACTIVE, value=0)
        self.char_current_state = service.configure_char(CHAR_CURRENT_HEATER_COOLER_STATE, value=HC_INACTIVE)
        target_valid_values = target_state_valid_values(self._hk_to_ha_target)
        initial_target = hk_target_mode(self._last_known_mode, self._hk_to_ha_target)
        if initial_target is None:
            initial_target = min(target_valid_values.values())
        self.char_target_state = service.configure_char(
            CHAR_TARGET_HEATER_COOLER_STATE,
            value=initial_target,
        )
        self.char_target_state.override_properties(valid_values=target_valid_values)
        self.char_target_state.allow_invalid_client_values = True
        self.char_current_temp = service.configure_char(CHAR_CURRENT_TEMPERATURE, value=21.0)

        self._min_temp, self._max_temp = temperature_range(attributes, self._unit)

        step_hk = self._step
        if self._unit != UnitOfTemperature.CELSIUS:
            step_hk = self._step * 5.0 / 9.0

        temp_properties = {
            PROP_MIN_VALUE: self._min_temp,
            PROP_MAX_VALUE: self._max_temp,
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

        self.char_speed: Characteristic | None = None
        if self.ordered_fan_speeds:
            self.char_speed = service.configure_char(
                CHAR_ROTATION_SPEED,
                value=HK_MAX_ROTATION_SPEED,
                properties={PROP_MIN_STEP: HK_MAX_ROTATION_SPEED / len(self.ordered_fan_speeds)},
            )

        self.swing_on_mode: str | None = None
        self.char_swing: Characteristic | None = None
        if features & ClimateEntityFeature.SWING_MODE and swing_mode_names:
            self.swing_on_mode = next(
                (mode for mode in swing_mode_names if swing_is_on(mode)),
                next(
                    (mode for mode in swing_mode_names if not swing_is_off(mode)),
                    swing_mode_names[0],
                ),
            )
            self.char_swing = service.configure_char(CHAR_SWING_MODE, value=0)

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
                CLIMATE_DOMAIN,
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
        calls, _ = plan_active_mode_change(
            char_values.get(CHAR_ACTIVE),
            char_values.get(CHAR_TARGET_HEATER_COOLER_STATE),
            currently_active,
            self._hk_to_ha_target,
            self._last_known_mode,
        )
        supported_modes = (
            _supported_hvac_modes(current_state.attributes.get(ATTR_HVAC_MODES) or []) if current_state else set()
        )
        previous_last_known_mode = self._last_known_mode
        for service_name, service_data in calls:
            if service_name != SERVICE_SET_HVAC_MODE:
                service_calls.append((service_name, service_data))
                continue

            mode = try_parse_enum(HVACMode, service_data.get(ATTR_HVAC_MODE))
            if mode in supported_modes:
                service_calls.append((service_name, service_data))
                self._last_known_mode = mode
                continue

            if (
                as_hap_integer(char_values.get(CHAR_ACTIVE)) == 1
                and not currently_active
                and previous_last_known_mode in supported_modes
            ):
                service_calls.append((SERVICE_SET_HVAC_MODE, {ATTR_HVAC_MODE: previous_last_known_mode}))

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
            high, low = resolve_dual_setpoints(
                cooling_temp,
                heating_temp,
                as_float(self.char_cool.value),
                as_float(self.char_heat.value),
                self._min_temp,
                self._max_temp,
            )
            temp_data: dict[str, float] = {}
            if high is not None:
                temp_data[ATTR_TARGET_TEMP_HIGH] = temperature_to_states(high, self._unit)
            if low is not None:
                temp_data[ATTR_TARGET_TEMP_LOW] = temperature_to_states(low, self._unit)
            if temp_data:
                service_calls.append((SERVICE_SET_TEMPERATURE, temp_data))
            return

        selected_temp = select_single_setpoint(
            current_state.state, cooling_temp, heating_temp, hk_temperature(attributes, ATTR_TEMPERATURE, self._unit)
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
            CLIMATE_DOMAIN,
            SERVICE_SET_FAN_MODE,
            {ATTR_ENTITY_ID: self.entity_id, ATTR_FAN_MODE: fan_mode},
        )

    def _set_swing_mode(self, swing_on: Any) -> None:
        """Set swing mode through the climate service."""
        if self.swing_on_mode is None:
            return

        swing_value = as_float(swing_on)
        if swing_value is None:
            return

        state = self.hass.states.get(self.entity_id)
        if not state:
            return

        swing_modes = state.attributes.get(ATTR_SWING_MODES, [])
        current_swing = state.attributes.get(ATTR_SWING_MODE)
        swing_enabled = bool(int(swing_value))
        if swing_enabled == swing_is_enabled(current_swing, swing_modes):
            return
        target_mode = resolve_swing_mode(swing_enabled, swing_modes, self.swing_on_mode)

        if target_mode is None or target_mode == current_swing:
            return

        self.async_call_service(
            CLIMATE_DOMAIN,
            SERVICE_SET_SWING_MODE,
            {ATTR_ENTITY_ID: self.entity_id, ATTR_SWING_MODE: target_mode},
        )

    @callback
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

    @callback
    def _async_update_fan_state(self, new_state: State) -> None:
        """Update fan speed and swing characteristics from entity state."""
        attributes = new_state.attributes
        if self.ordered_fan_speeds and self.char_speed is not None:
            percentage = percentage_for_fan_mode(self.ordered_fan_speeds, self.fan_modes, attributes.get(ATTR_FAN_MODE))
            if percentage is not None:
                self.char_speed.set_value(percentage)

        if self.char_swing is not None:
            self.char_swing.set_value(
                1 if swing_is_enabled(attributes.get(ATTR_SWING_MODE), attributes.get(ATTR_SWING_MODES, [])) else 0
            )


def register_heatercooler_type() -> None:
    """Register HeaterCooler with HomeKit accessory registry if absent."""
    if "HeaterCooler" not in TYPES:
        TYPES.register("HeaterCooler")(HeaterCooler)
