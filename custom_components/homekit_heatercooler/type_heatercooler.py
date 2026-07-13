"""Legacy HomeKit HeaterCooler accessory."""

import asyncio
from collections.abc import Callable, Coroutine
import logging
from typing import Any, Concatenate, NamedTuple, override

from pyhap.characteristic import Characteristic
from pyhap.const import CATEGORY_AIR_CONDITIONER, CATEGORY_HEATER

from homeassistant.components.climate import (
    ATTR_CURRENT_HUMIDITY,
    ATTR_CURRENT_TEMPERATURE,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_HVAC_MODES,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ATTR_TEMPERATURE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_SWING_MODE,
    SERVICE_SET_TEMPERATURE,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.homekit.accessories import TYPES
from homeassistant.const import ATTR_ENTITY_ID, ATTR_SUPPORTED_FEATURES
from homeassistant.core import State, callback
from homeassistant.util.enum import try_parse_enum

from .climate_base import CLIMATE_INACTIVE_STATES, HomeKitClimateAccessory
from .climate_util import as_float, as_hap_integer, temperature_attribute_to_homekit
from .const import (
    CHAR_ACTIVE,
    CHAR_COOLING_THRESHOLD_TEMPERATURE,
    CHAR_CURRENT_HEATER_COOLER_STATE,
    CHAR_CURRENT_HUMIDITY,
    CHAR_CURRENT_TEMPERATURE,
    CHAR_HEATING_THRESHOLD_TEMPERATURE,
    CHAR_NAME,
    CHAR_ROTATION_SPEED,
    CHAR_SWING_MODE,
    CHAR_TARGET_HEATER_COOLER_STATE,
    PROP_MAX_VALUE,
    PROP_MIN_STEP,
    PROP_MIN_VALUE,
    SERV_HEATER_COOLER,
    SERV_HUMIDITY_SENSOR,
)

_LOGGER = logging.getLogger(__name__)

HC_INACTIVE, HC_IDLE, HC_HEATING, HC_COOLING = range(4)
HC_TARGET_AUTO, HC_TARGET_HEAT, HC_TARGET_COOL = range(3)

HC_HASS_TO_HOMEKIT_TARGET = {
    HVACMode.HEAT: HC_TARGET_HEAT,
    HVACMode.COOL: HC_TARGET_COOL,
    HVACMode.HEAT_COOL: HC_TARGET_AUTO,
    HVACMode.AUTO: HC_TARGET_AUTO,
}

# Intentional legacy delta: Daikin reports Dry/Fan without a usable action, and
# the custom integration has always represented either as an active idle unit.
HC_HASS_TO_HOMEKIT_ACTION = {
    HVACAction.OFF: HC_INACTIVE,
    HVACAction.IDLE: HC_IDLE,
    HVACAction.HEATING: HC_HEATING,
    HVACAction.PREHEATING: HC_HEATING,
    HVACAction.COOLING: HC_COOLING,
    HVACAction.DRYING: HC_IDLE,
    HVACAction.FAN: HC_IDLE,
    HVACAction.DEFROSTING: HC_HEATING,
}

ACTION_HYSTERESIS = 0.25
RANGE_MODES = (HVACMode.HEAT_COOL, HVACMode.AUTO)


class ClimateServiceCall(NamedTuple):
    """A queued climate write and its accepted mode state."""

    service: str
    data: dict[str, Any]
    commit_mode: HVACMode | None = None
    pending_mode: HVACMode | None = None


def _locked_write[**P](
    func: Callable[Concatenate[HeaterCooler, P], Coroutine[Any, Any, None]],
) -> Callable[Concatenate[HeaterCooler, P], Coroutine[Any, Any, None]]:
    """Run a write coroutine under the accessory write lock."""

    async def _wrapper(
        self: HeaterCooler, /, *args: P.args, **kwargs: P.kwargs
    ) -> None:
        async with self._write_lock:
            await func(self, *args, **kwargs)

    return _wrapper


class HeaterCooler(HomeKitClimateAccessory):
    """Generate a HeaterCooler accessory for a legacy HomeKit bridge."""

    char_cool: Characteristic
    char_heat: Characteristic
    char_current_humidity: Characteristic

    def __init__(self, *args: Any) -> None:
        """Initialize the accessory."""
        super().__init__(*args)

        state = self.hass.states.get(self.entity_id)
        assert state
        attributes = state.attributes
        features = attributes.get(ATTR_SUPPORTED_FEATURES, 0)
        has_thresholds = bool(
            features
            & (
                ClimateEntityFeature.TARGET_TEMPERATURE
                | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
            )
        )

        hvac_modes = attributes.get(ATTR_HVAC_MODES, [])
        current_mode = try_parse_enum(HVACMode, state.state)
        self._supports_off = HVACMode.OFF in hvac_modes
        supports_auto = HVACMode.AUTO in hvac_modes or current_mode == HVACMode.AUTO
        supports_heat_cool = (
            HVACMode.HEAT_COOL in hvac_modes or current_mode == HVACMode.HEAT_COOL
        )
        can_cool = HVACMode.COOL in hvac_modes or supports_auto or supports_heat_cool
        can_heat = HVACMode.HEAT in hvac_modes or supports_auto or supports_heat_cool
        self.category = (
            CATEGORY_HEATER if can_heat and not can_cool else CATEGORY_AIR_CONDITIONER
        )

        if (not can_cool and not can_heat) or not (
            features & ClimateEntityFeature.TARGET_TEMPERATURE
        ):
            can_cool = can_heat = True
        self._has_cool_threshold = has_thresholds and can_cool
        self._has_heat_threshold = has_thresholds and can_heat

        self._hk_to_ha_target: dict[int, HVACMode] = {}
        if HVACMode.HEAT in hvac_modes:
            self._hk_to_ha_target[HC_TARGET_HEAT] = HVACMode.HEAT
        if HVACMode.COOL in hvac_modes:
            self._hk_to_ha_target[HC_TARGET_COOL] = HVACMode.COOL
        if supports_heat_cool:
            self._hk_to_ha_target[HC_TARGET_AUTO] = HVACMode.HEAT_COOL
        elif supports_auto:
            self._hk_to_ha_target[HC_TARGET_AUTO] = HVACMode.AUTO
        if not self._hk_to_ha_target:
            self._hk_to_ha_target[HC_TARGET_AUTO] = next(
                (mode for mode in hvac_modes if mode != HVACMode.OFF), HVACMode.OFF
            )

        chars = [
            CHAR_ACTIVE,
            CHAR_CURRENT_HEATER_COOLER_STATE,
            CHAR_TARGET_HEATER_COOLER_STATE,
            CHAR_CURRENT_TEMPERATURE,
        ]
        if self._has_cool_threshold:
            chars.append(CHAR_COOLING_THRESHOLD_TEMPERATURE)
        if self._has_heat_threshold:
            chars.append(CHAR_HEATING_THRESHOLD_TEMPERATURE)

        # Intentional legacy delta: fan_lane keeps RotationSpeed on the primary
        # service, instead of core's linked Fanv2 auto-control service.
        if self.ordered_fan_speeds:
            chars.append(CHAR_ROTATION_SPEED)
        if self.swing_on_mode is not None:
            chars.append(CHAR_SWING_MODE)

        service = self.add_preload_service(SERV_HEATER_COOLER, chars)
        self.char_active = service.configure_char(CHAR_ACTIVE, value=0)
        self.char_current_state = service.configure_char(
            CHAR_CURRENT_HEATER_COOLER_STATE, value=HC_INACTIVE
        )
        self._ha_to_hk_target = {
            ha_mode: hk_state for hk_state, ha_mode in self._hk_to_ha_target.items()
        }
        default_target = (
            HC_TARGET_AUTO
            if HC_TARGET_AUTO in self._hk_to_ha_target
            else next(iter(self._hk_to_ha_target))
        )
        self.char_target_state = self._configure_target_mode_char(
            service,
            CHAR_TARGET_HEATER_COOLER_STATE,
            default_target,
            self._ha_to_hk_target,
        )
        self._configure_current_temperature_char(service)

        if self._has_cool_threshold or self._has_heat_threshold:
            min_temp, max_temp = self.get_temperature_range(state)
            properties = {
                PROP_MIN_VALUE: min_temp,
                PROP_MAX_VALUE: max_temp,
            }
            default_temp = min(max(21.0, min_temp), max_temp)
            if self._has_cool_threshold:
                self.char_cool = service.configure_char(
                    CHAR_COOLING_THRESHOLD_TEMPERATURE,
                    value=default_temp,
                    properties=properties,
                )
            if self._has_heat_threshold:
                self.char_heat = service.configure_char(
                    CHAR_HEATING_THRESHOLD_TEMPERATURE,
                    value=default_temp,
                    properties=properties,
                )

        self.char_speed = None
        if self.ordered_fan_speeds:
            self.char_speed = service.configure_char(
                CHAR_ROTATION_SPEED,
                value=100,
                properties={PROP_MIN_STEP: 100 / len(self.ordered_fan_speeds)},
            )
        self.char_swing = None
        if self.swing_on_mode is not None:
            self.char_swing = service.configure_char(CHAR_SWING_MODE, value=0)

        self._has_humidity = ATTR_CURRENT_HUMIDITY in attributes
        if self._has_humidity:
            humidity_service = self.add_preload_service(SERV_HUMIDITY_SENSOR, CHAR_NAME)
            service.add_linked_service(humidity_service)
            humidity_service.configure_char(
                CHAR_NAME, value=f"{self.display_name} Humidity"
            )
            self.char_current_humidity = humidity_service.configure_char(
                CHAR_CURRENT_HUMIDITY, value=50
            )
        self.set_primary_service(service)

        if current_mode and self._hk_target_mode(current_mode) is not None:
            self._last_known_mode = current_mode
        else:
            self._last_known_mode = self._hk_to_ha_target[default_target]
        self._write_lock = asyncio.Lock()
        self._pending_mode: HVACMode | None = None
        self._last_reported_mode = current_mode
        self.async_update_state(state)
        service.setter_callback = self._set_chars

    def _set_chars(self, char_values: dict[str, Any]) -> None:
        """Schedule one atomic characteristic batch."""
        self.hass.async_create_task(
            self._async_apply_batch(char_values), eager_start=True
        )

    @_locked_write
    async def _async_apply_batch(self, char_values: dict[str, Any]) -> None:
        """Resolve and apply one characteristic batch in service-call order."""
        service_calls: list[ClimateServiceCall] = []
        current_state = self.hass.states.get(self.entity_id)
        active = (
            as_hap_integer(char_values[CHAR_ACTIVE])
            if CHAR_ACTIVE in char_values
            else None
        )
        target_mode = (
            as_hap_integer(char_values[CHAR_TARGET_HEATER_COOLER_STATE])
            if CHAR_TARGET_HEATER_COOLER_STATE in char_values
            else None
        )
        requested_mode = (
            self._hk_to_ha_target.get(target_mode) if target_mode is not None else None
        )
        if active == 1 and target_mode is None:
            requested_mode = self._last_known_mode

        if self._handle_active_mode_changes(
            active, target_mode, service_calls, current_state, requested_mode
        ):
            self._handle_temperature_changes(
                char_values,
                service_calls,
                current_state,
                requested_mode or self._pending_mode,
            )
            self._queue_fan_swing_changes(char_values, service_calls)

        for call in service_calls:
            reported_mode = self._last_reported_mode
            known_mode = self._last_known_mode
            if not await self.async_call_service_and_wait(
                CLIMATE_DOMAIN,
                call.service,
                {ATTR_ENTITY_ID: self.entity_id, **call.data},
            ):
                return
            if call.pending_mode and self._last_reported_mode == reported_mode:
                self._pending_mode = call.pending_mode
            if call.commit_mode and self._last_known_mode == known_mode:
                self._last_known_mode = call.commit_mode

    @override
    def _dispatch_climate_write(self, service: str, params: dict[str, Any]) -> None:
        """Serialize direct fan and swing writes behind batches."""
        self.hass.async_create_task(
            self._async_apply_locked_write(service, params), eager_start=True
        )

    @_locked_write
    async def _async_apply_locked_write(
        self, service: str, params: dict[str, Any]
    ) -> None:
        """Apply one direct write under the batch lock."""
        await self.async_call_service_and_wait(
            CLIMATE_DOMAIN, service, {ATTR_ENTITY_ID: self.entity_id, **params}
        )

    def _queue_fan_swing_changes(
        self,
        char_values: dict[str, Any],
        service_calls: list[ClimateServiceCall],
    ) -> None:
        """Queue fan and swing writes after HVAC and temperature writes."""
        if (
            CHAR_ROTATION_SPEED in char_values
            and (params := self._fan_speed_params(char_values[CHAR_ROTATION_SPEED]))
            is not None
        ):
            service_calls.append(ClimateServiceCall(SERVICE_SET_FAN_MODE, params))
        if (
            CHAR_SWING_MODE in char_values
            and (params := self._swing_mode_params(char_values[CHAR_SWING_MODE]))
            is not None
        ):
            service_calls.append(ClimateServiceCall(SERVICE_SET_SWING_MODE, params))

    def _handle_active_mode_changes(
        self,
        active: int | None,
        target_mode: int | None,
        service_calls: list[ClimateServiceCall],
        current_state: State | None,
        requested_mode: HVACMode | None,
    ) -> bool:
        """Queue active and mode changes, returning whether later writes apply."""
        if target_mode is not None and requested_mode is None:
            if (restore := self._hk_target_mode(self._last_known_mode)) is not None:
                self._reject_char_write(self.char_target_state, restore)

        if active == 0:
            if self._supports_off:
                service_calls.append(
                    ClimateServiceCall(
                        SERVICE_SET_HVAC_MODE,
                        {ATTR_HVAC_MODE: HVACMode.OFF},
                        commit_mode=requested_mode,
                        pending_mode=HVACMode.OFF,
                    )
                )
                return False
            self._reject_char_write(self.char_active, 1)

        if requested_mode and (
            target_mode is not None
            or current_state is None
            or self._pending_mode == HVACMode.OFF
            or current_state.state in CLIMATE_INACTIVE_STATES
        ):
            service_calls.append(
                ClimateServiceCall(
                    SERVICE_SET_HVAC_MODE,
                    {ATTR_HVAC_MODE: requested_mode},
                    commit_mode=requested_mode,
                    pending_mode=requested_mode,
                )
            )
        return True

    def _handle_temperature_changes(
        self,
        char_values: dict[str, Any],
        service_calls: list[ClimateServiceCall],
        current_state: State | None,
        requested_mode: HVACMode | None,
    ) -> None:
        """Queue a single or paired temperature write."""
        cooling_temp = (
            self._coerce_numeric_char_write(
                self.char_cool,
                char_values.get(CHAR_COOLING_THRESHOLD_TEMPERATURE),
            )
            if self._has_cool_threshold
            else None
        )
        heating_temp = (
            self._coerce_numeric_char_write(
                self.char_heat,
                char_values.get(CHAR_HEATING_THRESHOLD_TEMPERATURE),
            )
            if self._has_heat_threshold
            else None
        )
        if cooling_temp is None and heating_temp is None:
            return

        attributes = current_state.attributes if current_state else {}
        effective_mode: HVACMode | str | None = requested_mode or (
            current_state.state if current_state else None
        )
        use_range = (
            self._has_cool_threshold
            and self._has_heat_threshold
            and (
                ATTR_TARGET_TEMP_HIGH in attributes
                or ATTR_TARGET_TEMP_LOW in attributes
            )
            and (effective_mode in RANGE_MODES or ATTR_TEMPERATURE not in attributes)
        )
        if use_range:
            service_calls.append(
                ClimateServiceCall(
                    SERVICE_SET_TEMPERATURE,
                    self._dual_setpoint_params(
                        self.char_cool, self.char_heat, cooling_temp, heating_temp
                    ),
                )
            )
            return
        self._handle_single_temp_changes(
            service_calls, cooling_temp, heating_temp, current_state, effective_mode
        )

    def _handle_single_temp_changes(
        self,
        service_calls: list[ClimateServiceCall],
        cooling_temp: float | None,
        heating_temp: float | None,
        current_state: State | None,
        effective_mode: HVACMode | str | None,
    ) -> None:
        """Queue a single-temperature write for the effective HVAC mode."""
        if current_state is None:
            return
        selected_temp: float | None = None
        if effective_mode == HVACMode.COOL:
            selected_temp = cooling_temp
        elif effective_mode == HVACMode.HEAT:
            selected_temp = heating_temp
        elif (
            effective_mode in RANGE_MODES
            and cooling_temp is not None
            and heating_temp is not None
        ):
            target_temp = as_float(current_state.attributes.get(ATTR_TEMPERATURE))
            if target_temp is None:
                selected_temp = heating_temp
            else:
                target_temp_hk = self._temperature_to_homekit(target_temp)
                selected_temp = (
                    cooling_temp
                    if abs(cooling_temp - target_temp_hk)
                    > abs(heating_temp - target_temp_hk)
                    else heating_temp
                )
        elif cooling_temp is not None:
            selected_temp = cooling_temp
        elif heating_temp is not None:
            selected_temp = heating_temp

        if selected_temp is not None:
            service_calls.append(
                ClimateServiceCall(
                    SERVICE_SET_TEMPERATURE,
                    {ATTR_TEMPERATURE: self._temperature_to_states(selected_temp)},
                )
            )

    def _hk_target_mode(self, mode: HVACMode) -> int | None:
        """Map an HVAC mode to its exposed HomeKit target."""
        if (target := HC_HASS_TO_HOMEKIT_TARGET.get(mode)) in self._hk_to_ha_target:
            return target
        return self._ha_to_hk_target.get(mode)

    @callback
    @override
    def async_update_state(self, new_state: State) -> None:
        """Update characteristics from a climate state."""
        attributes = new_state.attributes
        current_mode = try_parse_enum(HVACMode, new_state.state)
        if current_mode is not None:
            if current_mode != self._last_reported_mode:
                self._pending_mode = None
            self._last_reported_mode = current_mode
        display_mode = self._pending_mode or current_mode
        if display_mode and (target := self._hk_target_mode(display_mode)) is not None:
            self._last_known_mode = display_mode
            self.char_target_state.set_value(target)

        if new_state.state in CLIMATE_INACTIVE_STATES:
            self.char_active.set_value(0)
            self.char_current_state.set_value(HC_INACTIVE)
        else:
            self.char_active.set_value(1)
            action = attributes.get(ATTR_HVAC_ACTION) or self._derive_action(
                new_state, current_mode
            )
            self.char_current_state.set_value(
                HC_HASS_TO_HOMEKIT_ACTION.get(action, HC_INACTIVE)
            )

        self._update_current_temperature_char(new_state)
        self._update_temperature_thresholds(new_state)
        if (
            self._has_humidity
            and (humidity := as_float(attributes.get(ATTR_CURRENT_HUMIDITY)))
            is not None
        ):
            self.char_current_humidity.set_value(humidity)
        self._update_fan_speed_char(attributes)
        self._update_swing_char(attributes)

    def _update_temperature_thresholds(self, state: State) -> None:
        """Update available threshold characteristics."""
        if not self._has_cool_threshold and not self._has_heat_threshold:
            return
        attributes = state.attributes
        supports_dual_temp = (
            attributes.get(ATTR_TARGET_TEMP_HIGH) is not None
            or attributes.get(ATTR_TARGET_TEMP_LOW) is not None
        )
        if supports_dual_temp:
            if self._has_cool_threshold:
                self._update_temperature_char(
                    self.char_cool, state, ATTR_TARGET_TEMP_HIGH
                )
            if self._has_heat_threshold:
                self._update_temperature_char(
                    self.char_heat, state, ATTR_TARGET_TEMP_LOW
                )
            return

        if (
            target_temp := temperature_attribute_to_homekit(
                state, ATTR_TEMPERATURE, self._unit
            )
        ) is not None:
            if self._has_cool_threshold:
                self.char_cool.set_value(target_temp)
            if self._has_heat_threshold:
                self.char_heat.set_value(target_temp)

    def _derive_action(self, state: State, mode: HVACMode | None) -> HVACAction:
        """Derive heating or cooling when an integration omits hvac_action."""
        current_temp = as_float(state.attributes.get(ATTR_CURRENT_TEMPERATURE))
        if current_temp is None or mode is None:
            return HVACAction.IDLE
        attributes = state.attributes
        if mode in RANGE_MODES:
            cool_above = as_float(attributes.get(ATTR_TARGET_TEMP_HIGH))
            heat_below = as_float(attributes.get(ATTR_TARGET_TEMP_LOW))
            if cool_above is None and heat_below is None:
                cool_above = heat_below = as_float(attributes.get(ATTR_TEMPERATURE))
        elif mode == HVACMode.COOL:
            cool_above = as_float(attributes.get(ATTR_TEMPERATURE))
            heat_below = None
        elif mode == HVACMode.HEAT:
            cool_above = None
            heat_below = as_float(attributes.get(ATTR_TEMPERATURE))
        else:
            return HVACAction.IDLE

        current_hk = self._temperature_to_homekit(current_temp)
        if (
            cool_above is not None
            and current_hk
            > self._temperature_to_homekit(cool_above) + ACTION_HYSTERESIS
        ):
            return HVACAction.COOLING
        if (
            heat_below is not None
            and current_hk
            < self._temperature_to_homekit(heat_below) - ACTION_HYSTERESIS
        ):
            return HVACAction.HEATING
        return HVACAction.IDLE


def register_legacy_type() -> None:
    """Register the bundled type only on cores without native support."""
    TYPES.register("HeaterCooler")(HeaterCooler)
