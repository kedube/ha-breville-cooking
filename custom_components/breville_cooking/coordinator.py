"""Appliance list over REST, live appliance state over the websocket."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable
import contextlib
from dataclasses import dataclass, field
import logging
import time
from typing import TYPE_CHECKING, Any, TypeVar

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import TemperatureConverter

from .api import (
    ApplianceSocket,
    BrevilleAuthError,
    BrevilleClient,
    BrevilleError,
    MODEL_CSJ100,
    StopRecipeReason,
    auto_start_update,
    parse_message,
)
from .appliance import (
    FINISH_WAIT_MODELS,
    MODELS,
    ApplianceStatus,
    AutoStart,
    AutoStartAction,
    CookSettings,
    CookState,
    LimitProblem,
    StateTracker,
    build_edit,
    build_finish_wait,
    build_manual_steps,
    build_next_step,
    cook_limit_problem,
    default_settings,
    firmware_for,
    parse_status,
)
from .const import (
    APPLIANCE_REFRESH_INTERVAL,
    CONF_ALLOW_UNTESTED_CONTROL,
    CONF_SHOW_SIDEBAR_PANEL,
    DEFAULT_SHOW_SIDEBAR_PANEL,
    DOMAIN,
    MESSAGE_LOG_SIZE,
    WS_RECONNECT_FACTOR,
    WS_RECONNECT_MAX,
    WS_RECONNECT_MIN,
)

if TYPE_CHECKING:
    from . import BrevilleConfigEntry

_LOGGER = logging.getLogger(__name__)
_T = TypeVar("_T")

# Seconds a cook stays Ready for food before Start timer automatically presses Continue.
AUTO_START_GRACE_S = 3.0


def sidebar_panel_enabled(entry: ConfigEntry) -> bool:
    """The sidebar panel shows the entry's appliances unless it's turned off."""
    return entry.options.get(CONF_SHOW_SIDEBAR_PANEL, DEFAULT_SHOW_SIDEBAR_PANEL) is not False


@dataclass
class Appliance:
    """One supported appliance and its latest state."""

    serial: str
    model: str
    name: str | None
    item_number: str | None
    settings: CookSettings
    state: dict[str, Any] = field(default_factory=dict)
    status: ApplianceStatus = field(default_factory=ApplianceStatus)
    # False once the appliance list no longer includes it.
    on_account: bool = True
    # Raw websocket messages, newest last, for diagnostics.
    messages: deque[dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=MESSAGE_LOG_SIZE)
    )
    # A cook Home Assistant started whose timer it starts itself (see AutoStart).
    auto_start: AutoStart | None = None


class BrevilleCoordinator(DataUpdateCoordinator[dict[str, Appliance]]):
    """Keeps every appliance on the account up to date."""

    config_entry: BrevilleConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: BrevilleConfigEntry, client: BrevilleClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=APPLIANCE_REFRESH_INTERVAL,
        )
        self.client = client
        self.appliances: dict[str, Appliance] = {}
        self.connected = False
        # While listeners hear of one appliance's new state, its serial: other
        # appliances' entities have nothing to update.
        self.updating_serial: str | None = None
        self._tracker = StateTracker()
        self._socket: ApplianceSocket | None = None
        self._unsupported: set[str] = set()
        # A message that couldn't be read is logged in full once: a field that
        # breaks parsing tends to come back in every message after it.
        self._message_error_logged = False

    async def _async_update_data(self) -> dict[str, Appliance]:
        try:
            result = await self.client.get_appliances()
        except BrevilleAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (BrevilleError, aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Error fetching appliances: {err}") from err

        added = []
        listed: set[str] = set()
        for raw in result["appliances"]:
            serial, model = raw.get("serialNumber"), raw.get("model")
            if not isinstance(serial, str) or not serial or not isinstance(model, str):
                continue
            if model not in MODELS:
                if serial not in self._unsupported:
                    self._unsupported.add(serial)
                    _LOGGER.info("Ignoring unsupported appliance model %s", model)
                continue
            listed.add(serial)
            if (appliance := self.appliances.get(serial)) is None:
                appliance = self.appliances[serial] = Appliance(
                    serial, model, raw.get("name"), raw.get("itemNumber"),
                    default_settings(model),
                )
                added.append(appliance)
            elif raw.get("name"):
                appliance.name = raw["name"]
        # Appliances that left the account go unavailable; their devices can
        # then be deleted (async_remove_config_entry_device).
        for serial, appliance in self.appliances.items():
            appliance.on_account = serial in listed
        if added and (socket := self._socket) is not None and socket.connected:
            for appliance in added:
                # A failure means the socket is going down, and the reconnect
                # subscribes every appliance: it mustn't fail the refresh.
                with contextlib.suppress(
                    BrevilleError, aiohttp.ClientError, ConnectionError, TimeoutError
                ):
                    await socket.subscribe(appliance.serial, appliance.model)
        return self.appliances

    async def async_remove_appliance(self, serial: str) -> None:
        """Forget an appliance whose device was deleted."""
        if self.appliances.pop(serial, None) is None:
            return
        if self._socket is not None and self._socket.connected:
            with contextlib.suppress(BrevilleError, aiohttp.ClientError):
                await self._socket.unsubscribe(serial)

    # -- websocket -----------------------------------------------------------

    @callback
    def async_start_websocket(self) -> None:
        self.config_entry.async_create_background_task(
            self.hass, self._run_websocket(), f"{DOMAIN} websocket"
        )

    async def _run_websocket(self) -> None:
        delay = WS_RECONNECT_MIN
        while True:
            socket = self.client.websocket()
            try:
                await socket.connect()
                self._socket = socket
                self._set_connected(True)
                delay = WS_RECONNECT_MIN
                for appliance in list(self.appliances.values()):
                    await socket.subscribe(appliance.serial, appliance.model)
                async for msg in socket.messages():
                    self._safely_handle_message(msg)
                _LOGGER.debug("Websocket closed")
            except BrevilleAuthError:
                _LOGGER.warning("Breville session expired; re-authentication required")
                self.config_entry.async_start_reauth(self.hass)
                return
            except (BrevilleError, aiohttp.ClientError, ConnectionError, TimeoutError) as err:
                _LOGGER.debug("Websocket error: %s", err)
            except Exception:  # keep the live connection alive whatever happens
                _LOGGER.exception("Unexpected error in the Breville websocket")
            finally:
                self._socket = None
                self._set_connected(False)
                await socket.close()
            await asyncio.sleep(delay)
            delay = min(delay * WS_RECONNECT_FACTOR, WS_RECONNECT_MAX)

    @property
    def answers_pings(self) -> bool:
        """Whether the cloud answers pings on the current connection, so a drop is noticed."""
        return self._socket is not None and self._socket.answers_pings

    @callback
    def _set_connected(self, connected: bool) -> None:
        if self.connected != connected:
            self.connected = connected
            self.async_update_listeners()

    @callback
    def _safely_handle_message(self, msg: Any) -> None:
        """Handle a message, ignoring one that can't be read.

        One appliance's malformed message mustn't end the connection, which
        would take every appliance on the account offline, and again with the
        full report on every reconnect if the field stays in the shadow.
        """
        try:
            self._handle_message(msg)
        except Exception:
            if not self._message_error_logged:
                self._message_error_logged = True
                _LOGGER.exception(
                    "Ignoring a message from Breville's cloud that couldn't be read;"
                    " later ones are logged at debug level"
                )
            else:
                _LOGGER.debug("Ignoring a message that couldn't be read", exc_info=True)

    @callback
    def _handle_message(self, msg: Any) -> None:
        # Keep every message for the appliance, even ones that are ignored or
        # out of date: the sequence is what diagnostics are for.
        serial = msg.get("serialNumber") if isinstance(msg, dict) else None
        if isinstance(serial, str) and (logged := self.appliances.get(serial)) is not None:
            logged.messages.append(
                {"at": dt_util.utcnow().isoformat(timespec="seconds"), "message": msg}
            )
        update = parse_message(msg)
        if update is None or (appliance := self.appliances.get(update.serial)) is None:
            return
        if not self._tracker.apply(update, appliance.model):
            return
        appliance.state = self._tracker.state(update.serial)
        firmware = appliance.status.firmware
        appliance.status = parse_status(appliance.model, appliance.state, previous=appliance.status)
        if appliance.status.firmware and appliance.status.firmware != firmware:
            self._update_sw_version(appliance)
        self._check_auto_start(appliance)
        self.updating_serial = appliance.serial
        try:
            self.async_update_listeners()
        finally:
            self.updating_serial = None

    @callback
    def _check_auto_start(self, appliance: Appliance) -> None:
        """Press Continue for a cook that should have started its timer by itself."""
        if (auto := appliance.auto_start) is None:
            return
        action = auto.step(appliance.status, time.monotonic())
        if action is AutoStartAction.WAIT:
            return
        appliance.auto_start = None
        if action is AutoStartAction.PRESS:
            self.config_entry.async_create_background_task(
                self.hass,
                self._auto_continue(appliance, auto.cook_id),
                f"{DOMAIN} start timer automatically",
            )

    async def _auto_continue(self, appliance: Appliance, cook_id: str | None) -> None:
        # A moment's grace: an appliance that starts its own timer could report
        # Ready for food first.
        await asyncio.sleep(AUTO_START_GRACE_S)
        status = appliance.status
        if (
            status.state is not CookState.READY
            or status.cook_id != cook_id
            or self.appliances.get(appliance.serial) is not appliance
        ):
            return
        _LOGGER.debug("At temperature: starting the timer, as Start timer automatically is on")
        try:
            await self.async_finish_wait(appliance)
        except HomeAssistantError as err:
            _LOGGER.warning(
                "Couldn't start the %s's timer automatically; press Continue: %s",
                appliance.name or MODELS[appliance.model].product, err,
            )

    @callback
    def _update_sw_version(self, appliance: Appliance) -> None:
        # By config entry: async_get_device stops working in Home Assistant 2027.8, and its
        # replacements don't exist in the oldest versions this supports.
        registry = dr.async_get(self.hass)
        for device in dr.async_entries_for_config_entry(registry, self.config_entry.entry_id):
            if (DOMAIN, appliance.serial) in device.identifiers:
                registry.async_update_device(device.id, sw_version=appliance.status.firmware)
                return

    # -- commands --------------------------------------------------------------

    def control_allowed(self, appliance: Appliance) -> bool:
        """Whether cooks may be started or changed (stopping always is)."""
        return MODELS[appliance.model].tested or bool(
            self.config_entry.options.get(CONF_ALLOW_UNTESTED_CONTROL)
        )

    def _ensure_control_allowed(self, appliance: Appliance) -> None:
        if not self.control_allowed(appliance):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="untested_control",
                translation_placeholders={"product": MODELS[appliance.model].product},
            )

    async def async_start_cook(
        self, appliance: Appliance, settings: CookSettings | None = None
    ) -> None:
        self._ensure_control_allowed(appliance)
        settings = settings or appliance.settings
        if (problem := cook_limit_problem(appliance.model, settings)) is not None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key=problem.key,
                translation_placeholders=self._limit_placeholders(problem),
            )
        try:
            steps = build_manual_steps(appliance.model, settings)
        except ValueError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="start_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        # The steps ask for it too, but a Joule ignores that. Like the app, a
        # second request arms its timer. Should a sous vide still wait for the
        # food, Continue is pressed for it (finish-wait).
        appliance.auto_start = (
            AutoStart(time.monotonic())
            if settings.auto_start_timer and appliance.model in FINISH_WAIT_MODELS
            else None
        )
        try:
            await self._call(
                self.client.load_manual_recipe(
                    appliance.serial,
                    appliance.model,
                    firmware_for(appliance.model, appliance.state),
                    steps,
                    locale=self._locale(),
                )
            )
        except HomeAssistantError:
            appliance.auto_start = None
            raise
        if settings.auto_start_timer and appliance.model == MODEL_CSJ100:
            await self._arm_auto_start(appliance)

    async def _arm_auto_start(self, appliance: Appliance) -> None:
        """The app's second request for a Joule cook: start the timer at temperature.

        The cook has started either way, so a failure is only logged; Continue
        is pressed for it if it waits for the food.
        """
        try:
            await self.client.update_cook(
                appliance.serial, appliance.model, [auto_start_update()], uuid="", step=0
            )
        except (BrevilleError, aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.warning(
                "The %s didn't take Start timer automatically, so Continue will be "
                "pressed for it at temperature: %s",
                appliance.name or MODELS[appliance.model].product, err,
            )

    async def async_stop_cook(self, appliance: Appliance) -> None:
        appliance.auto_start = None
        await self._call(
            self.client.stop_recipe(
                appliance.serial,
                appliance.model,
                firmware=firmware_for(appliance.model, appliance.state),
                reason=StopRecipeReason.CANCEL,
            )
        )

    async def async_finish_wait(self, appliance: Appliance) -> None:
        """The app's on-screen button: food in, or food out."""
        self._ensure_control_allowed(appliance)
        if appliance.model in FINISH_WAIT_MODELS:
            await self._call(
                self.client.finish_wait(
                    appliance.serial,
                    appliance.model,
                    build_finish_wait(appliance.model, appliance.state),
                )
            )
            return
        try:
            step = build_next_step(appliance.state)
        except ValueError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="edit_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await self._call(
            self.client.send_step(
                appliance.serial,
                appliance.model,
                firmware_for(appliance.model, appliance.state),
                step.recipe_id,
                step.step_index,
            )
        )

    async def async_edit_cook(
        self,
        appliance: Appliance,
        *,
        temperature_c: float | None = None,
        duration_s: int | None = None,
    ) -> None:
        self._ensure_control_allowed(appliance)
        if appliance.status.state is CookState.DONE:
            # A Joule whose timer had run out showed the new setpoint but held
            # the old temperature. The Joule Turbo hasn't been tried, so it's
            # treated the same rather than show a target nobody heats to.
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="cook_over")
        if not MODELS[appliance.model].can_edit_cook:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="stop_cook_first"
            )
        try:
            edit = build_edit(
                appliance.model, appliance.state, appliance.status,
                temperature_c=temperature_c, duration_s=duration_s,
            )
        except ValueError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="edit_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        if edit.csj_program is not None:
            await self._call(
                self.client.csj_update_program(appliance.serial, edit.csj_program)
            )
        else:
            await self._call(
                self.client.update_cook(
                    appliance.serial, appliance.model, edit.updates,
                    uuid=edit.uuid, step=edit.step,
                )
            )

    async def _call(self, request: Awaitable[_T]) -> _T:
        try:
            return await request
        except BrevilleAuthError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="auth_expired"
            ) from err
        except (BrevilleError, aiohttp.ClientError, TimeoutError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="request_failed",
                translation_placeholders={"error": str(err)},
            ) from err

    def _limit_placeholders(self, problem: LimitProblem) -> dict[str, str]:
        """The limits as the error shows them: minutes, or degrees in Home Assistant's unit."""
        if problem.key == "duration_out_of_range":
            return {"min": str(int(problem.low) // 60), "max": str(int(problem.high) // 60)}
        unit = self.hass.config.units.temperature_unit

        def degrees(celsius: float) -> str:
            value = TemperatureConverter.convert(celsius, UnitOfTemperature.CELSIUS, unit)
            return f"{round(value, 1):g} {unit}"

        return {"min": degrees(problem.low), "max": degrees(problem.high)}

    def _locale(self) -> str:
        language = self.hass.config.language or "en"
        if "-" in language:
            return language
        country = self.hass.config.country
        return f"{language}-{country}" if country else "en-US"
