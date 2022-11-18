"""Home Assistant entity descriptions."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import VSmartUpdateCoordinator
from .vsmart import VSmartDevice, VSmartDeviceReport, VSmartDeviceStatus
from .const import DOMAIN


class VSmartEntity(CoordinatorEntity[VSmartUpdateCoordinator]):
    """VSmart base entity type."""

    def __init__(
        self,
        coordinator: VSmartUpdateCoordinator,
        config_entry: ConfigEntry,
        device_id: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self.device_id = device_id

    @property
    def device_info(self) -> DeviceInfo:
        """Device information for the spa providing this entity."""

        device_info: VSmartDevice = self.coordinator.data[self.device_id].device

        return DeviceInfo(
            identifiers={(DOMAIN, self.device_id)},
            name=device_info.alias,
            model=device_info.product_name,
            manufacturer="VSmart",
        )

    @property
    def device_status(self) -> VSmartDeviceStatus | None:
        """Get status data for the spa providing this entity."""
        device_report: VSmartDeviceReport = self.coordinator.data.get(self.device_id)
        if device_report:
            return device_report.status
        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.device_status is not None and self.device_status.online
