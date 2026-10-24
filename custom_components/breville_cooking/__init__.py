"""The Breville+ Cooking integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, service
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import BrevilleClient, Tokens
from .appliance import CONVECTION_ALL, OVEN_MODES
from .const import (
    ATTR_AUTO_START_TIMER,
    ATTR_CONVECTION,
    ATTR_DURATION,
    ATTR_KEEP_WARM,
    ATTR_LEVEL,
    ATTR_MODE,
    ATTR_TEMPERATURE,
    DOMAIN,
    SERVICE_START_COOK,
)
from .coordinator import BrevilleCoordinator

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

START_COOK_SCHEMA = {
    vol.Optional(ATTR_TEMPERATURE): vol.Coerce(float),
    vol.Optional(ATTR_DURATION): cv.positive_time_period,
    vol.Optional(ATTR_MODE): vol.In(list(OVEN_MODES)),
    vol.Optional(ATTR_CONVECTION): vol.In(list(CONVECTION_ALL)),
    vol.Optional(ATTR_LEVEL): vol.In(["low", "medium", "high"]),
    vol.Optional(ATTR_AUTO_START_TIMER): cv.boolean,
    vol.Optional(ATTR_KEEP_WARM): cv.boolean,
}

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

type BrevilleConfigEntry = ConfigEntry[BrevilleCoordinator]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the start_cook service (targets an appliance's Cook switch)."""
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_START_COOK,
        entity_domain=SWITCH_DOMAIN,
        schema=START_COOK_SCHEMA,
        func="async_start_cook_service",
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: BrevilleConfigEntry) -> bool:
    """Set up Breville+ Cooking from a config entry."""

    def save_tokens(tokens: Tokens) -> None:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, **tokens.as_dict()}
        )

    client = BrevilleClient(
        async_get_clientsession(hass),
        Tokens.from_dict(entry.data),
        on_tokens_updated=save_tokens,
    )
    coordinator = BrevilleCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.async_start_websocket()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BrevilleConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
