"""Diagnostics: raw appliance state, to help support new models and firmware."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL
from homeassistant.core import HomeAssistant

from . import BrevilleConfigEntry

TO_REDACT = {
    CONF_EMAIL,
    "id_token",
    "refresh_token",
    "access_token",
    "macAddress",
    "circulatorAddress",
    "cookId",
    "cookUUID",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BrevilleConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "websocket_connected": coordinator.connected,
        "appliances": [
            {
                "serial": f"…{appliance.serial[-4:]}",
                "model": appliance.model,
                "item_number": appliance.item_number,
                "status": async_redact_data(asdict(appliance.status), TO_REDACT),
                "settings": asdict(appliance.settings),
                "reported": async_redact_data(appliance.state, TO_REDACT),
            }
            for appliance in coordinator.appliances.values()
        ],
    }
