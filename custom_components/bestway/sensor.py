"""Switch platform support."""
from __future__ import annotations

from homeassistant.components.sensor import  SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.const import (
    TEMP_CELSIUS,
)

from custom_components.bestway.bestway import BestwayApi, BestwayDeviceStatus

from . import BestwayUpdateCoordinator
from .const import DOMAIN
from .entity import BestwayEntity

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch entities."""
    coordinator: BestwayUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities = [
        BestwaySensor(coordinator, config_entry, device_id)
        for device_id in coordinator.data.keys()
    ]
    async_add_entities(entities)


class BestwaySensor(BestwayEntity, SwitchEntity):
    """Bestway sensor entity."""

    _attr_name = "VSmart Flow Temperature Sensor"
    _attr_device_class = "temperature"
    _native_unit_of_measurement = TEMP_CELSIUS

    def __init__(
        self,
        coordinator: BestwayUpdateCoordinator,
        config_entry: ConfigEntry,
        device_id: str,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, config_entry, device_id)
        self._attr_unique_id = f"{device_id}_temperature_sensor"

    @property
    def update(self) -> float | None:
        """Return the flow temperature."""
        if not self.device_status:
            return None
        return self.device_status.flow_temp

