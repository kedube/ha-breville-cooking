"""Sensors for Breville+ appliances."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import BrevilleConfigEntry
from .appliance import ERROR_OPTIONS, MODEL_BOV950, REPORTED_MODE_OPTIONS, CookState
from .coordinator import Appliance
from .entity import BrevilleEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class BrevilleSensorDescription(SensorEntityDescription):
    value_fn: Callable[[Appliance], StateType | datetime]
    models: frozenset[str] | None = None
    always_available: bool = False


SENSORS: tuple[BrevilleSensorDescription, ...] = (
    BrevilleSensorDescription(
        key="status",
        device_class=SensorDeviceClass.ENUM,
        options=[state.value for state in CookState],
        value_fn=lambda a: a.status.state.value,
        always_available=True,
    ),
    BrevilleSensorDescription(
        key="current_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda a: a.status.current_temp_c,
    ),
    BrevilleSensorDescription(
        key="time_remaining",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        value_fn=lambda a: a.status.time_remaining_s,
    ),
    BrevilleSensorDescription(
        key="cook_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda a: a.status.ends_at,
    ),
    BrevilleSensorDescription(
        key="active_mode",
        device_class=SensorDeviceClass.ENUM,
        options=REPORTED_MODE_OPTIONS,
        models=frozenset({MODEL_BOV950}),
        value_fn=lambda a: a.status.mode if a.status.cooking else None,
    ),
    BrevilleSensorDescription(
        key="error",
        device_class=SensorDeviceClass.ENUM,
        options=ERROR_OPTIONS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda a: a.status.error,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BrevilleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        BrevilleSensor(coordinator, appliance, description)
        for appliance in coordinator.appliances.values()
        for description in SENSORS
        if description.models is None or appliance.model in description.models
    )


class BrevilleSensor(BrevilleEntity, SensorEntity):
    entity_description: BrevilleSensorDescription

    def __init__(self, coordinator, appliance, description: BrevilleSensorDescription) -> None:
        super().__init__(coordinator, appliance, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        if self.entity_description.always_available:
            return self.coordinator.connected
        return super().available

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.appliance)
