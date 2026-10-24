"""Continue button: the app's virtual button press (food in / food out)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BrevilleConfigEntry
from .appliance import WAITING_STATES
from .entity import BrevilleEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BrevilleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        ContinueButton(coordinator, appliance, "continue")
        for appliance in coordinator.appliances.values()
    )


class ContinueButton(BrevilleEntity, ButtonEntity):
    """Starts the timer once the food is in, or finishes once it's out."""

    @property
    def available(self) -> bool:
        return super().available and self.appliance.status.state in WAITING_STATES

    async def async_press(self) -> None:
        await self.coordinator.async_finish_wait(self.appliance)
