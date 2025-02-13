"""Binary sensor platform."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VSmartUpdateCoordinator
from .const import DOMAIN
from .entity import VSmartEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities."""
    coordinator: VSmartUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities: list[VSmartEntity] = []
    for device_id in coordinator.data.keys():
        entities.extend(
            [
                VSmartConnectivitySensor(coordinator, config_entry, device_id),
            ]
        )

    async_add_entities(entities)


class VSmartBinarySensor(VSmartEntity, BinarySensorEntity):
    """VSmart binary sensor."""

    entity_description: BinarySensorEntityDescription

    def __init__(
        self,
        coordinator: VSmartUpdateCoordinator,
        config_entry: ConfigEntry,
        device_id: str,
        description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, config_entry, device_id)
        self.entity_description = description
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_unique_id = f"{device_id}_{description.key}"


class VSmartConnectivitySensor(VSmartBinarySensor):
    """Sensor to indicate whether a spa is currently online."""

    def __init__(
        self,
        coordinator: VSmartUpdateCoordinator,
        config_entry: ConfigEntry,
        device_id: str,
    ) -> None:
        """Initialize sensor."""
        super().__init__(
            coordinator,
            config_entry,
            device_id,
            BinarySensorEntityDescription(
                key="connected",
                device_class=BinarySensorDeviceClass.CONNECTIVITY,
                entity_category=EntityCategory.DIAGNOSTIC,
                name="VSmart Connected",
            ),
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if the spa is online."""
        return self.device_status is not None and self.device_status.online

    @property
    def available(self) -> bool:
        """Return True, as the connectivity sensor is always available."""
        return True