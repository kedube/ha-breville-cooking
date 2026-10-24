"""Diagnostics: raw appliance state and recent traffic, to support new models and firmware.

Testers post these publicly, and untested models may report fields nobody has
seen, so fields are masked by name pattern rather than a fixed list. The
account email and appliance nicknames are masked wherever they appear.
"""

from __future__ import annotations

from dataclasses import asdict
import re
from typing import Any

from homeassistant.const import CONF_EMAIL
from homeassistant.core import HomeAssistant

from . import BrevilleConfigEntry
from .appliance import MODELS

REDACTED = "**REDACTED**"
SENSITIVE_KEY = re.compile(
    r"token|password|secret|e-?mail|phone|address|street|postal|zip|ssid|"
    r"(first|last|given|family|user)_?name|user_?id|^sub$|mfa|latitude|longitude|"
    r"(^|_)ip(_|$)|uuid|cook_?id|circulator_?id",
    re.IGNORECASE,
)


def short_serial(serial: Any) -> str:
    return f"…{str(serial)[-4:]}"


def redact(value: Any, secrets: frozenset[str] = frozenset()) -> Any:
    """Copy of value with sensitive fields and secret values masked.

    Serial numbers keep their last four characters, to tell appliances apart.
    """
    if isinstance(value, dict):
        return {key: _redact_field(str(key), item, secrets) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [redact(item, secrets) for item in value]
    if isinstance(value, str) and value in secrets:
        return REDACTED
    return value


def _redact_field(key: str, value: Any, secrets: frozenset[str]) -> Any:
    if value is None or value == "":
        return value
    if "serial" in key.lower():
        return short_serial(value)
    if SENSITIVE_KEY.search(key):
        return REDACTED
    return redact(value, secrets)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BrevilleConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    secrets = frozenset(
        value
        for value in (
            entry.data.get(CONF_EMAIL),
            entry.unique_id,
            *(appliance.name for appliance in coordinator.appliances.values()),
        )
        if value
    )
    return {
        "entry": redact(dict(entry.data), secrets),
        "options": dict(entry.options),
        "websocket_connected": coordinator.connected,
        "recent_requests": redact(coordinator.client.recent_requests, secrets),
        "appliances": [
            {
                "serial": short_serial(appliance.serial),
                "model": appliance.model,
                "item_number": appliance.item_number,
                "tested": MODELS[appliance.model].tested,
                "status": redact(asdict(appliance.status), secrets),
                "settings": asdict(appliance.settings),
                "reported": redact(appliance.state, secrets),
                "recent_messages": redact(list(appliance.messages), secrets),
            }
            for appliance in coordinator.appliances.values()
        ],
    }
