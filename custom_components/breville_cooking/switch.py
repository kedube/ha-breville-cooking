"""Cook switch (start/stop) and cook options."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF, STATE_ON, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util.unit_conversion import TemperatureConverter

from . import BrevilleConfigEntry
from .appliance import MODEL_BOV950, OVEN_MODES, oven_mode_defaults
from .const import (
    ATTR_AUTO_START_TIMER,
    ATTR_CONVECTION,
    ATTR_DURATION,
    ATTR_KEEP_WARM,
    ATTR_LEVEL,
    ATTR_MODE,
    ATTR_TEMPERATURE,
    DOMAIN,
)
from .entity import BrevilleEntity, async_add_appliance_entities
from .select import LEVEL_OPTIONS

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BrevilleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    def entities_for(coordinator, appliance) -> list[BrevilleSwitch]:
        entities: list[BrevilleSwitch] = [
            CookSwitch(coordinator, appliance, "cook"),
            AutoStartTimerSwitch(coordinator, appliance, "auto_start_timer"),
        ]
        if appliance.model == MODEL_BOV950:
            entities.append(KeepWarmSwitch(coordinator, appliance, "keep_warm"))
            entities.append(FrozenSwitch(coordinator, appliance, "frozen"))
        return entities

    async_add_appliance_entities(entry, async_add_entities, entities_for)


class BrevilleSwitch(BrevilleEntity, SwitchEntity):
    async def async_start_cook_service(self, **kwargs: Any) -> None:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="target_cook_switch"
        )


class CookSwitch(BrevilleSwitch):
    """On while a cook runs; turning it on starts one with the current settings."""

    @property
    def is_on(self) -> bool:
        return self.appliance.status.cooking

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_start_cook(self.appliance)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_stop_cook(self.appliance)

    async def async_start_cook_service(self, **kwargs: Any) -> None:
        """breville_cooking.start_cook: start a cook with explicit settings."""
        appliance = self.appliance
        settings = replace(appliance.settings)
        if (mode := kwargs.get(ATTR_MODE)) is not None:
            if appliance.model != MODEL_BOV950:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="mode_oven_only"
                )
            defaults = oven_mode_defaults(OVEN_MODES[mode])
            defaults.auto_start_timer = settings.auto_start_timer
            defaults.keep_warm = settings.keep_warm
            settings = defaults
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            settings.temperature_c = TemperatureConverter.convert(
                temperature,
                self.hass.config.units.temperature_unit,
                UnitOfTemperature.CELSIUS,
            )
        if (duration := kwargs.get(ATTR_DURATION)) is not None:
            settings.duration_s = int(duration.total_seconds()) if isinstance(duration, timedelta) else int(duration)
        if (convection := kwargs.get(ATTR_CONVECTION)) is not None:
            settings.convection = convection
        if (level := kwargs.get(ATTR_LEVEL)) is not None:
            mode = OVEN_MODES.get(settings.mode or "")
            levels = LEVEL_OPTIONS.get(mode.type, {}) if mode else {}
            if level not in levels:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="level_not_for_mode",
                    translation_placeholders={"level": level},
                )
            settings.level = int(levels[level])
        if ATTR_AUTO_START_TIMER in kwargs:
            settings.auto_start_timer = kwargs[ATTR_AUTO_START_TIMER]
        if ATTR_KEEP_WARM in kwargs:
            settings.keep_warm = kwargs[ATTR_KEEP_WARM]
        await self.coordinator.async_start_cook(appliance, settings)


class BrevilleOptionSwitch(BrevilleSwitch, RestoreEntity):
    """A cook option stored in the appliance's settings."""

    _attr_entity_category = EntityCategory.CONFIG
    _field: str

    @property
    def available(self) -> bool:
        return self.cloud_available

    @property
    def is_on(self) -> bool:
        return bool(getattr(self.appliance.settings, self._field))

    async def async_turn_on(self, **kwargs: Any) -> None:
        setattr(self.appliance.settings, self._field, True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        setattr(self.appliance.settings, self._field, False)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Not from "unavailable": that says nothing about the setting.
        if (last := await self.async_get_last_state()) is not None and last.state in (
            STATE_ON,
            STATE_OFF,
        ):
            setattr(self.appliance.settings, self._field, last.state == STATE_ON)


class AutoStartTimerSwitch(BrevilleOptionSwitch):
    """Start the timer when the setpoint is reached instead of waiting for food."""

    _field = "auto_start_timer"


class KeepWarmSwitch(BrevilleOptionSwitch):
    """Keep food warm when an oven cook finishes."""

    _field = "keep_warm"


class FrozenSwitch(BrevilleOptionSwitch):
    """Cook from frozen, for the oven modes that offer it (pizza, cookies, reheat).

    Choosing a mode resets it to that mode's default.
    """

    _field = "frozen"

    @property
    def available(self) -> bool:
        mode = OVEN_MODES.get(self.appliance.settings.mode or "")
        return super().available and mode is not None and mode.frozen_default is not None
