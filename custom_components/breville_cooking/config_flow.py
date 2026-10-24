"""Config flow for Breville+ Cooking."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BrevilleAuthError, BrevilleClient, BrevilleError, BrevilleMfaRequired, Tokens
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema({vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str})
REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): str})


class BrevilleConfigFlow(ConfigFlow, domain=DOMAIN):
    """Log in with a Breville account."""

    VERSION = 1

    async def _login(self, email: str, password: str) -> tuple[Tokens | None, dict[str, str]]:
        client = BrevilleClient(async_get_clientsession(self.hass))
        try:
            return await client.login(email, password), {}
        except BrevilleMfaRequired:
            return None, {"base": "mfa_not_supported"}
        except BrevilleAuthError:
            return None, {"base": "invalid_auth"}
        except (BrevilleError, aiohttp.ClientError, TimeoutError):
            return None, {"base": "cannot_connect"}
        except Exception:
            _LOGGER.exception("Unexpected error logging in to Breville")
            return None, {"base": "unknown"}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            tokens, errors = await self._login(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
            if tokens:
                await self.async_set_unique_id(tokens.user_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_EMAIL],
                    data={CONF_EMAIL: user_input[CONF_EMAIL], **tokens.as_dict()},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA, {CONF_EMAIL: (user_input or {}).get(CONF_EMAIL)}
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            tokens, errors = await self._login(entry.data[CONF_EMAIL], user_input[CONF_PASSWORD])
            if tokens:
                await self.async_set_unique_id(tokens.user_id)
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    entry, data_updates=tokens.as_dict()
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )
