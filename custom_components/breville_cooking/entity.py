"""Base entity for Breville+ appliances."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .appliance import MODELS
from .const import DOMAIN
from .coordinator import Appliance, BrevilleCoordinator


class BrevilleEntity(CoordinatorEntity[BrevilleCoordinator]):
    """An entity belonging to one appliance."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BrevilleCoordinator, appliance: Appliance, key: str) -> None:
        super().__init__(coordinator)
        self._serial = appliance.serial
        self._attr_unique_id = f"{appliance.serial}_{key}"
        self._attr_translation_key = key
        info = MODELS[appliance.model]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, appliance.serial)},
            manufacturer=info.manufacturer,
            model=info.product,
            model_id=appliance.item_number or appliance.model,
            name=appliance.name or info.product,
            serial_number=appliance.serial,
        )

    @property
    def appliance(self) -> Appliance:
        return self.coordinator.appliances[self._serial]

    @property
    def available(self) -> bool:
        # Live state comes from the websocket; a failed appliance-list refresh
        # alone shouldn't make the appliance unavailable.
        return self.coordinator.connected and self.appliance.status.online
