"""Sensor platform support."""
from __future__ import annotations

from homeassistant.components.sensor import  SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.const import (
    UnitOfTemperature,
)

from custom_components.vsmart.vsmart import VSmartApi, VSmartDeviceStatus

from . import VSmartUpdateCoordinator
from .const import DOMAIN
from .entity import VSmartEntity

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator: VSmartUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities = [
        VSmartSensor(coordinator, config_entry, device_id)
        for device_id in coordinator.data.keys()
    ]
    async_add_entities(entities)


class VSmartSensor(VSmartEntity, SensorEntity):
    """VSmart sensor entity."""

    _attr_name = "VSmart Flow Temperature Sensor"
    _attr_device_class = "temperature"
    _attr_state_class = "measurement"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(
        self,
        coordinator: VSmartUpdateCoordinator,
        config_entry: ConfigEntry,
        device_id: str,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, config_entry, device_id)
        self._attr_unique_id = f"{device_id}_temperature_sensor"

    @property
    def native_value(self) -> float | None:
        """Return the flow temperature."""
        if not self.device_status:
            return None
        return self.device_status.flow_temp

