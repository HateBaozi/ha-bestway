"""Water Heater platform support."""
from __future__ import annotations

from typing import Any

from homeassistant.components.water_heater import WaterHeaterEntity, WaterHeaterEntityFeature,WaterHeaterEntityEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    PRECISION_HALVES,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VSmartUpdateCoordinator
from .vsmart import TemperatureUnit
from .const import (
    DHW_ON,
    DHW_OFF,
    DOMAIN,
)
from .entity import VSmartEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up water heater entities."""
    coordinator: VSmartUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities = [
        VSmartWaterHeater(coordinator, config_entry, device_id)
        for device_id in coordinator.data.keys()
    ]
    async_add_entities(entities)

class VSmartWaterHeater(VSmartEntity, WaterHeaterEntity):
    """The main water heater entity."""

    entity_description: WaterHeaterEntityEntityDescription
    
    _attr_name = "VSmart Water Heater"
    _attr_supported_features = WaterHeaterEntityFeature.TARGET_TEMPERATURE|WaterHeaterEntityFeature.OPERATION_MODE
    _attr_operation_list = [DHW_ON,DHW_OFF]
    _attr_precision = PRECISION_HALVES
    _attr_target_temperature_step = 0.5
    _attr_max_temp = 60
    _attr_min_temp = 35

    def __init__(
        self,
        coordinator: VSmartUpdateCoordinator,
        config_entry: ConfigEntry,
        device_id: str,
    ) -> None:
        """Initialize thermostat."""
        super().__init__(coordinator, config_entry, device_id)
        self._attr_unique_id = f"{device_id}_water_heater"

    @property
    def state(self) -> str | None:
        """Return the current state."""
        return self.current_operation

    @property
    def current_operation(self) ->  str | None:
        """Return the current mode (ON or OFF)."""
        if not self.device_status:
            return None
        return DHW_ON if self.device_status.dhw_power else DHW_OFF

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        if not self.device_status:
            return None
        return self.device_status.dhw_temp_now

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        if not self.device_status:
            return None
        return self.device_status.dhw_temp_set

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement used by the platform."""
        if (
            not self.device_status
            or self.device_status.temp_set_unit == TemperatureUnit.CELSIUS
        ):
            return str(UnitOfTemperature.CELSIUS)
        else:
            return str(UnitOfTemperature.FAHRENHEIT)

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set new target operation mode."""
        should_heat = True if operation_mode == DHW_ON else False
        await self.coordinator.api.set_dhw(self.device_id, should_heat)
        await self.coordinator.async_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a new target temperature."""
        target_temperature = kwargs.get(ATTR_TEMPERATURE)
        if target_temperature is None:
            return

        await self.coordinator.api.set_dhw_temp(self.device_id, target_temperature)
        await self.coordinator.async_refresh()
