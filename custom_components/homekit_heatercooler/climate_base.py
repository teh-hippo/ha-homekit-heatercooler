"""Shared climate accessory support for the legacy HeaterCooler."""

from collections.abc import Mapping
import logging
from typing import Any

from pyhap.characteristic import Characteristic
from pyhap.const import CATEGORY_THERMOSTAT
from pyhap.service import Service

from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_HVAC_MODES,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_SWING_MODE,
    ATTR_SWING_MODES,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_SWING_MODE,
    SWING_OFF,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.homekit.accessories import HomeAccessory
from homeassistant.components.homekit.const import (
    ATTR_DISPLAY_NAME,
    ATTR_VALUE,
    EVENT_HOMEKIT_CHANGED,
)
from homeassistant.components.homekit.util import (
    temperature_to_homekit,
    temperature_to_states,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SERVICE,
    ATTR_SUPPORTED_FEATURES,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Context, State
from homeassistant.exceptions import HomeAssistantError

from .climate_util import (
    as_float,
    as_hap_integer,
    fan_mode_to_speed,
    fan_speed_to_mode,
    get_fan_modes_and_speeds,
    get_swing_off_mode,
    get_swing_on_mode,
    get_temperature_range_from_state,
    has_swing_off_mode,
    is_swing_on,
    resolve_target_temp_range,
    temperature_attribute_to_homekit,
)
from .const import (
    CHAR_CURRENT_TEMPERATURE,
    CONF_FAN_LANE,
    DEFAULT_FAN_LANE,
    PROP_MAX_VALUE,
    PROP_MIN_VALUE,
)

_LOGGER = logging.getLogger(__name__)

CLIMATE_INACTIVE_STATES = frozenset({HVACMode.OFF, STATE_UNAVAILABLE, STATE_UNKNOWN})


class HomeKitClimateAccessory(HomeAccessory):
    """Base class for the legacy climate accessory types."""

    char_speed: Characteristic | None
    char_swing: Characteristic | None
    char_current_temp: Characteristic

    def __init__(self, *args: Any) -> None:
        """Initialize shared climate state."""
        super().__init__(*args, category=CATEGORY_THERMOSTAT)
        self._unit = self.hass.config.units.temperature_unit

        state = self.hass.states.get(self.entity_id)
        assert state
        attributes = state.attributes
        features = attributes.get(ATTR_SUPPORTED_FEATURES, 0)

        self.fan_modes: dict[str, str] = {}
        self.ordered_fan_speeds: list[str] = []
        if features & ClimateEntityFeature.FAN_MODE:
            fan_lane = self.config.get(CONF_FAN_LANE, DEFAULT_FAN_LANE)
            self.fan_modes, self.ordered_fan_speeds = get_fan_modes_and_speeds(
                attributes, fan_lane
            )

        self.swing_on_mode: str | None = None
        self.swing_off_mode = SWING_OFF
        if features & ClimateEntityFeature.SWING_MODE and has_swing_off_mode(
            attributes
        ):
            self.swing_on_mode = get_swing_on_mode(attributes)
            self.swing_off_mode = get_swing_off_mode(attributes)

        self._reload_on_change_attrs.extend(
            (
                ATTR_MIN_TEMP,
                ATTR_MAX_TEMP,
                ATTR_FAN_MODES,
                ATTR_SWING_MODES,
                ATTR_HVAC_MODES,
            )
        )

    def get_temperature_range(self, state: State) -> tuple[float, float]:
        """Return the valid HomeKit temperature range."""
        return get_temperature_range_from_state(
            state, self._unit, DEFAULT_MIN_TEMP, DEFAULT_MAX_TEMP
        )

    async def async_call_service_and_wait(
        self,
        domain: str,
        service: str,
        service_data: dict[str, Any],
        value: Any | None = None,
    ) -> bool:
        """Call a service synchronously and restore state after a failure."""
        event_data = {
            ATTR_ENTITY_ID: service_data.get(ATTR_ENTITY_ID, self.entity_id),
            ATTR_DISPLAY_NAME: self.display_name,
            ATTR_SERVICE: service,
            ATTR_VALUE: value,
        }
        context = Context()
        self.hass.bus.async_fire(EVENT_HOMEKIT_CHANGED, event_data, context=context)
        try:
            await self.hass.services.async_call(
                domain, service, service_data, blocking=True, context=context
            )
        except HomeAssistantError as err:
            _LOGGER.warning(
                "%s: %s.%s failed (%s); re-syncing HomeKit state",
                self.entity_id,
                domain,
                service,
                err,
            )
        except Exception:
            _LOGGER.exception(
                "%s: %s.%s raised unexpectedly; re-syncing HomeKit state",
                self.entity_id,
                domain,
                service,
            )
        else:
            return True

        try:
            if (state := self.hass.states.get(self.entity_id)) is not None:
                self.async_update_state(state)
        except Exception:
            _LOGGER.exception("%s: re-syncing HomeKit state failed", self.entity_id)
        return False

    def _configure_current_temperature_char(self, service: Service) -> None:
        """Configure the current temperature characteristic."""
        self.char_current_temp = service.configure_char(
            CHAR_CURRENT_TEMPERATURE, value=21.0
        )

    def _configure_target_mode_char(
        self,
        service: Service,
        char_name: str,
        value: int,
        valid_values: dict[Any, int],
    ) -> Characteristic:
        """Configure a target mode characteristic with constrained values."""
        char = service.configure_char(char_name, value=value)
        char.override_properties(valid_values=valid_values)
        char.allow_invalid_client_values = True
        return char

    def _reject_char_write(self, char: Characteristic, value: Any) -> None:
        """Restore a characteristic after rejecting a client write."""
        char.value = value
        char.notify()

    def _coerce_numeric_char_write(
        self, char: Characteristic, value: Any
    ) -> float | None:
        """Return the finite value pyhap stored for a raw numeric write."""
        if as_float(value) is None:
            return None
        return as_float(char.to_valid_value(value))

    def _dispatch_climate_write(self, service: str, params: dict[str, Any]) -> None:
        """Dispatch a non-batched climate service call."""
        self.async_call_service(
            CLIMATE_DOMAIN, service, {ATTR_ENTITY_ID: self.entity_id, **params}
        )

    def _update_temperature_char(
        self, char: Characteristic, state: State, attr: str
    ) -> None:
        """Update a characteristic from a state temperature."""
        if (
            value := temperature_attribute_to_homekit(state, attr, self._unit)
        ) is not None:
            char.set_value(value)

    def _update_current_temperature_char(self, state: State) -> None:
        """Update the current temperature characteristic."""
        self._update_temperature_char(
            self.char_current_temp, state, ATTR_CURRENT_TEMPERATURE
        )

    def _dual_setpoint_params(
        self,
        cool_char: Characteristic,
        heat_char: Characteristic,
        new_high: float | None,
        new_low: float | None,
    ) -> dict[str, float]:
        """Return bounded paired temperature targets."""
        high, low = resolve_target_temp_range(
            cool_char.value,
            heat_char.value,
            new_high,
            new_low,
            cool_char.properties[PROP_MIN_VALUE],
            cool_char.properties[PROP_MAX_VALUE],
        )
        return {
            ATTR_TARGET_TEMP_HIGH: temperature_to_states(high, self._unit),
            ATTR_TARGET_TEMP_LOW: temperature_to_states(low, self._unit),
        }

    def _temperature_to_homekit(self, temperature: float) -> float:
        """Convert a state temperature to HomeKit units."""
        return temperature_to_homekit(temperature, self._unit)

    def _temperature_to_states(self, temperature: float) -> float:
        """Convert a HomeKit temperature to state units."""
        return temperature_to_states(temperature, self._unit)

    def _fan_speed_params(self, speed: Any) -> dict[str, Any] | None:
        """Return fan-mode service data for a rotation speed."""
        if self.char_speed is None:
            return None
        speed_value = as_hap_integer(
            self._coerce_numeric_char_write(self.char_speed, speed)
        )
        if (
            speed_value is None
            or not self.ordered_fan_speeds
            or not 0 < speed_value <= 100
        ):
            return None
        return {
            ATTR_FAN_MODE: fan_speed_to_mode(
                self.ordered_fan_speeds, self.fan_modes, speed_value
            )
        }

    def _set_fan_speed(self, speed: Any) -> None:
        """Set the fan mode for a rotation speed."""
        if (params := self._fan_speed_params(speed)) is not None:
            self._dispatch_climate_write(SERVICE_SET_FAN_MODE, params)

    def _swing_mode_params(self, swing_on: Any) -> dict[str, Any] | None:
        """Return swing-mode service data for a binary HomeKit write."""
        swing_value = as_hap_integer(swing_on)
        if self.swing_on_mode is None or swing_value not in (0, 1):
            return None
        return {
            ATTR_SWING_MODE: self.swing_on_mode if swing_value else self.swing_off_mode
        }

    def _set_swing_mode(self, swing_on: Any) -> None:
        """Set the climate swing mode."""
        if (params := self._swing_mode_params(swing_on)) is not None:
            self._dispatch_climate_write(SERVICE_SET_SWING_MODE, params)

    def _update_fan_speed_char(self, attributes: Mapping[str, Any]) -> None:
        """Update the rotation-speed characteristic."""
        if (
            self.char_speed is not None
            and self.ordered_fan_speeds
            and (
                speed := fan_mode_to_speed(
                    self.ordered_fan_speeds, attributes.get(ATTR_FAN_MODE)
                )
            )
            is not None
        ):
            self.char_speed.set_value(speed)

    def _update_swing_char(self, attributes: Mapping[str, Any]) -> None:
        """Update the swing characteristic."""
        if self.char_swing is None or self.swing_on_mode is None:
            return
        swing_mode = attributes.get(ATTR_SWING_MODE)
        enabled = is_swing_on(swing_mode) or (
            isinstance(swing_mode, str)
            and swing_mode.lower() == self.swing_on_mode.lower()
        )
        self.char_swing.set_value(1 if enabled else 0)
