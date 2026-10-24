"""Integration setup, live updates and commands, with the cloud client mocked."""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from datetime import timedelta
import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.json import ExtendedJSONEncoder
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.breville_cooking import async_remove_config_entry_device
from custom_components.breville_cooking.api import BrevilleAuthError
from custom_components.breville_cooking.appliance import OVEN_MODES
from custom_components.breville_cooking.const import CONF_ALLOW_UNTESTED_CONTROL, DOMAIN
from custom_components.breville_cooking.diagnostics import (
    REDACTED,
    async_get_config_entry_diagnostics,
)

from .common import make_jwt

JOULE, OVEN = "J123456", "A950123456"
# The profile claims a real Breville login token carries.
PROFILE = {
    "email": "me@example.com", "name": "Pat Example", "nickname": "patex",
    "customer_id": "C-123456", "https://breville.com/crm_user_id": "CRM-98765",
}
APPLIANCES = {
    "appliances": [
        {"model": "CSJ100", "serialNumber": JOULE, "name": "Countertop", "itemNumber": "CS10001"},
        {"model": "BOV950", "serialNumber": OVEN, "name": "Kitchen Oven", "itemNumber": "BOV950BSS"},
        {"model": "BES995", "serialNumber": "espresso1", "name": "Espresso"},
    ],
    "ownedModels": ["CSJ100", "BOV950", "BES995"],
}


class FakeSocket:
    """Stands in for ApplianceSocket; tests push messages into it."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[Any] = asyncio.Queue()
        self.subscribed: list[tuple[str, str]] = []
        self.unsubscribed: list[str] = []
        self.connected = False
        self.connect_error: Exception | None = None

    async def connect(self) -> None:
        if self.connect_error:
            raise self.connect_error
        self.connected = True

    async def subscribe(self, serial: str, model: str) -> None:
        self.subscribed.append((serial, model))

    async def unsubscribe(self, serial: str) -> None:
        self.unsubscribed.append(serial)

    async def messages(self):
        while (msg := await self.queue.get()) is not None:
            yield msg

    async def close(self) -> None:
        self.connected = False


def csj(state: str, step: int, **extra: Any) -> dict:
    csj.ts += 1000
    return {
        "serialNumber": JOULE,
        "messageType": "applianceDataPoint",
        "version": str(1792805500000 + csj.ts),
        "data": {
            "state": state, "model": "CSJ100", "programStep": step, "bathTemp": 55.1,
            "setPoint": 56.0, "cookTime": 300, "timeRemaining": 0, "errorState": 0,
            "eventReason": 0, "cookId": "cook1", "guideId": "manual_x",
            "firmwareVersion": "123", "espFirmwareVersion": "52", "hardwareOptions": 1,
            "timestamp": csj.ts, **extra,
        },
    }


csj.ts = 1_000_000

OVEN_IDLE = {
    "serialNumber": OVEN,
    "messageType": "stateReport",
    "version": 10,
    "data": {
        "reported": {
            "state": "idle", "model": "BOV950", "heaters": [{"cur_temp": 22.0, "state": 0}],
            "door": {"state": 1}, "appliance": {"mode": 3}, "errors": [],
            "firmware": {"comm_mcu": "1.0", "host_mcu": "2.0"},
        }
    },
}


@pytest.fixture
def socket() -> FakeSocket:
    return FakeSocket()


@pytest.fixture
def client_class(socket: FakeSocket) -> Generator[MagicMock]:
    with patch("custom_components.breville_cooking.BrevilleClient", autospec=True) as cls:
        mock = cls.return_value
        mock.get_appliances.return_value = APPLIANCES
        mock.websocket.return_value = socket
        yield cls


@pytest.fixture
def client(client_class: MagicMock) -> MagicMock:
    return client_class.return_value


async def flush(hass: HomeAssistant) -> None:
    for _ in range(5):
        await asyncio.sleep(0)
    await hass.async_block_till_done()


async def push(hass: HomeAssistant, socket: FakeSocket, *messages: dict) -> None:
    for msg in messages:
        socket.queue.put_nowait(msg)
    await flush(hass)


@pytest.fixture
async def entry(hass: HomeAssistant, client: MagicMock, socket: FakeSocket) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="Salesforce|1",
        title="me@example.com",
        data={"email": "me@example.com", "id_token": make_jwt(**PROFILE), "refresh_token": "refresh"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await flush(hass)
    return entry


async def call(hass: HomeAssistant, domain: str, service: str, entity_id: str, **data: Any) -> None:
    await hass.services.async_call(
        domain, service, {ATTR_ENTITY_ID: entity_id, **data}, blocking=True
    )


async def test_setup_creates_entities_for_supported_models(
    hass: HomeAssistant, entry: MockConfigEntry, socket: FakeSocket
) -> None:
    assert entry.state is ConfigEntryState.LOADED
    assert socket.subscribed == [(JOULE, "CSJ100"), (OVEN, "BOV950")]
    registry = er.async_get(hass)
    joule = {e.entity_id for e in er.async_entries_for_config_entry(registry, entry.entry_id) if e.unique_id.startswith(JOULE)}
    assert joule == {
        "sensor.countertop_status", "sensor.countertop_temperature", "sensor.countertop_time_remaining",
        "sensor.countertop_cook_end", "sensor.countertop_error", "binary_sensor.countertop_cooking",
        "binary_sensor.countertop_problem", "number.countertop_target_temperature",
        "number.countertop_cook_time", "switch.countertop_cook",
        "switch.countertop_start_timer_automatically", "button.countertop_continue",
    }
    for entity_id in ("select.kitchen_oven_mode", "select.kitchen_oven_convection",
                      "binary_sensor.kitchen_oven_door", "sensor.kitchen_oven_active_mode",
                      "switch.kitchen_oven_keep_warm"):
        assert registry.async_get(entity_id), entity_id
    # Connected, but no state from the Joule yet.
    assert hass.states.get("sensor.countertop_status").state == "offline"
    assert hass.states.get("switch.countertop_cook").state == STATE_UNAVAILABLE

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_sage_account(
    hass: HomeAssistant, client_class: MagicMock, socket: FakeSocket
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="Salesforce|1",
        data={"email": "me@example.com", "brand": "sage", "id_token": make_jwt(), "refresh_token": "r"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await flush(hass)
    assert client_class.call_args.kwargs["endpoints"].app_channel == "sageJoule"
    devices = dr.async_get(hass)
    assert devices.async_get_device(identifiers={(DOMAIN, OVEN)}).manufacturer == "Sage"
    assert devices.async_get_device(identifiers={(DOMAIN, JOULE)}).manufacturer == "ChefSteps"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_appliances_added_and_removed_later(
    hass: HomeAssistant, entry: MockConfigEntry, socket: FakeSocket, client: MagicMock
) -> None:
    coordinator = entry.runtime_data
    turbo = {"model": "BSV600", "serialNumber": "T600123", "name": "Turbo", "itemNumber": "BSV600BSS"}
    client.get_appliances.return_value = {
        "appliances": [APPLIANCES["appliances"][0], turbo], "ownedModels": [],
    }
    await coordinator.async_refresh()
    await flush(hass)

    # The new appliance appears without a reload.
    assert hass.states.get("sensor.turbo_status") is not None
    assert hass.states.get("switch.turbo_cook") is not None
    assert ("T600123", "BSV600") in socket.subscribed

    # The oven has left the account: unavailable, and its device can be deleted.
    assert hass.states.get("sensor.kitchen_oven_status").state == STATE_UNAVAILABLE
    devices = dr.async_get(hass)
    joule = devices.async_get_device(identifiers={(DOMAIN, JOULE)})
    oven = devices.async_get_device(identifiers={(DOMAIN, OVEN)})
    assert await async_remove_config_entry_device(hass, entry, joule) is False
    assert await async_remove_config_entry_device(hass, entry, oven) is True
    assert OVEN not in coordinator.appliances and socket.unsubscribed == [OVEN]
    await hass.config_entries.async_unload(entry.entry_id)


async def test_joule_cook_lifecycle(
    hass: HomeAssistant, entry: MockConfigEntry, socket: FakeSocket, client: MagicMock
) -> None:
    await push(hass, socket, csj("IDLE", 0, setPoint=None, cookId=None, bathTemp=21.2))
    assert hass.states.get("sensor.countertop_status").state == "idle"
    assert hass.states.get("sensor.countertop_temperature").state == "21.2"
    assert hass.states.get("switch.countertop_cook").state == STATE_OFF
    assert hass.states.get("button.countertop_continue").state == STATE_UNAVAILABLE

    # Idle: settings only, no cloud call.
    await call(hass, "number", "set_value", "number.countertop_target_temperature", value=55)
    await call(hass, "number", "set_value", "number.countertop_cook_time", value=45)
    client.csj_update_program.assert_not_awaited()

    await call(hass, "switch", "turn_on", "switch.countertop_cook")
    serial, model, firmware, steps = client.load_manual_recipe.await_args.args
    assert (serial, model, firmware) == (JOULE, "CSJ100", {"commFirmware": "52", "ctrlFirmware": "123"})
    assert steps[0]["holdingTemperature"] == 55.0
    assert steps[0]["phases"][0]["seconds"] == 2700
    assert client.load_manual_recipe.await_args.kwargs["locale"] == "en-US"

    await push(hass, socket, csj("ACTIVE", 2))
    assert hass.states.get("sensor.countertop_status").state == "ready"
    assert hass.states.get("switch.countertop_cook").state == STATE_ON
    await call(hass, "button", "press", "button.countertop_continue")
    client.finish_wait.assert_awaited_once_with(JOULE, "CSJ100")

    await push(hass, socket, csj("ACTIVE", 3, timeRemaining=240))
    assert hass.states.get("sensor.countertop_status").state == "cooking"
    assert float(hass.states.get("sensor.countertop_time_remaining").state) == 4
    assert hass.states.get("number.countertop_cook_time").state == "4"
    assert hass.states.get("sensor.countertop_cook_end").state != "unknown"

    # Running: changing the temperature edits the cook, keeping its timer.
    await call(hass, "number", "set_value", "number.countertop_target_temperature", value=57)
    serial, program = client.csj_update_program.await_args.args
    assert program["setPoint"] == 57.0 and program["cookTime"] == 240
    assert program["programMetadata"] == {"cookId": "cook1", "guideId": "manual_x"}

    await call(hass, "switch", "turn_off", "switch.countertop_cook")
    assert client.stop_recipe.await_args.args == (JOULE, "CSJ100")
    assert client.stop_recipe.await_args.kwargs["firmware"] == {"commFirmware": "52", "ctrlFirmware": "123"}

    await push(hass, socket, csj("ACTIVE", 5, errorState=2, eventReason=4))
    assert hass.states.get("binary_sensor.countertop_problem").state == STATE_ON
    assert hass.states.get("sensor.countertop_error").state == "tipped_over"

    await push(hass, socket, csj("OFFLINE", 0))
    assert hass.states.get("sensor.countertop_status").state == "offline"
    assert hass.states.get("number.countertop_target_temperature").state == STATE_UNAVAILABLE
    await hass.config_entries.async_unload(entry.entry_id)


OVEN_ROASTING = {
    "serialNumber": OVEN, "messageType": "changeReport", "version": 11,
    "data": {"reported": {"state": "active", "cookUUID": "c-9", "currentStep": 1,
                          "appliance": {"mode": 4},
                          "heaters": [{"cur_temp": 150, "temp_sp": 190, "state": 2}]}},
}


async def test_untested_models_are_monitor_only(
    hass: HomeAssistant, entry: MockConfigEntry, socket: FakeSocket, client: MagicMock
) -> None:
    await push(hass, socket, OVEN_IDLE)
    with pytest.raises(ServiceValidationError) as err:
        await call(hass, "switch", "turn_on", "switch.kitchen_oven_cook")
    assert err.value.translation_key == "untested_control"
    assert str(err.value).startswith("Control of the Joule Oven Air Fryer Pro hasn't been tested")
    with pytest.raises(ServiceValidationError):
        await call(hass, DOMAIN, "start_cook", "switch.kitchen_oven_cook", temperature=200)
    client.load_manual_recipe.assert_not_awaited()

    # A cook started on the oven itself can be watched and stopped, not changed.
    await push(hass, socket, OVEN_ROASTING)
    assert hass.states.get("switch.kitchen_oven_cook").state == STATE_ON
    with pytest.raises(ServiceValidationError):
        await call(hass, "number", "set_value", "number.kitchen_oven_target_temperature", value=200)
    client.update_cook.assert_not_awaited()
    await call(hass, "switch", "turn_off", "switch.kitchen_oven_cook")
    client.stop_recipe.assert_awaited_once()

    # The option applies straight away, without a reload.
    hass.config_entries.async_update_entry(entry, options={CONF_ALLOW_UNTESTED_CONTROL: True})
    await call(hass, "number", "set_value", "number.kitchen_oven_target_temperature", value=200)
    client.update_cook.assert_awaited_once()
    await hass.config_entries.async_unload(entry.entry_id)


async def test_oven_settings_and_start_service(
    hass: HomeAssistant, entry: MockConfigEntry, socket: FakeSocket, client: MagicMock
) -> None:
    hass.config_entries.async_update_entry(entry, options={CONF_ALLOW_UNTESTED_CONTROL: True})
    await push(hass, socket, OVEN_IDLE)
    assert hass.states.get("select.kitchen_oven_mode").state == "bake"
    assert hass.states.get("binary_sensor.kitchen_oven_door").state == STATE_OFF
    assert hass.states.get("select.kitchen_oven_level").state == STATE_UNAVAILABLE

    await call(hass, "select", "select_option", "select.kitchen_oven_mode", option="air_fry")
    temp = hass.states.get("number.kitchen_oven_target_temperature")
    assert (temp.state, temp.attributes["min"], temp.attributes["max"]) == ("205.0", 150, 250)
    assert hass.states.get("select.kitchen_oven_convection").attributes["options"] == ["super"]

    await call(hass, "select", "select_option", "select.kitchen_oven_mode", option="broil")
    assert hass.states.get("number.kitchen_oven_target_temperature").state == STATE_UNAVAILABLE
    await call(hass, "select", "select_option", "select.kitchen_oven_level", option="medium")

    await call(
        hass, DOMAIN, "start_cook", "switch.kitchen_oven_cook",
        mode="roast", temperature=190, duration=timedelta(minutes=50),
    )
    serial, model, firmware, steps = client.load_manual_recipe.await_args.args
    assert (serial, model) == (OVEN, "BOV950")
    assert firmware == {"commFirmware": "1.0", "ctrlFirmware": "2.0"}
    assert [s["stepType"] for s in steps] == ["default", "default", "aBitMore", "keepWarm"]
    cook = steps[1]["phases"][0]
    assert (cook["mode"], cook["temperatureCelsius"], cook["seconds"]) == ("roast", 190, 3000)
    # The service doesn't change the entities' own settings.
    assert hass.states.get("select.kitchen_oven_mode").state == "broil"

    with pytest.raises(ServiceValidationError):
        await call(hass, DOMAIN, "start_cook", "switch.kitchen_oven_keep_warm", temperature=200)

    # Cooking: the mode can't change, and the temperature edits the cook.
    await push(hass, socket, OVEN_ROASTING)
    assert hass.states.get("sensor.kitchen_oven_active_mode").state == "roast"
    with pytest.raises(ServiceValidationError):
        await call(hass, "select", "select_option", "select.kitchen_oven_mode", option="bake")
    await call(hass, "number", "set_value", "number.kitchen_oven_target_temperature", value=200)
    client.update_cook.assert_awaited_once_with(
        OVEN, "BOV950", [{"name": "cookSetPoint", "value": 200.0}], uuid="c-9", step=1
    )
    await hass.config_entries.async_unload(entry.entry_id)


async def test_cloud_errors_become_ha_errors(
    hass: HomeAssistant, entry: MockConfigEntry, socket: FakeSocket, client: MagicMock
) -> None:
    from custom_components.breville_cooking.api import BrevilleApiError

    await push(hass, socket, csj("IDLE", 0, setPoint=None, cookId=None))
    client.load_manual_recipe.side_effect = BrevilleApiError("POST", "u", 500, "oops")
    with pytest.raises(HomeAssistantError):
        await call(hass, "switch", "turn_on", "switch.countertop_cook")
    await hass.config_entries.async_unload(entry.entry_id)


async def test_websocket_auth_failure_starts_reauth(
    hass: HomeAssistant, client: MagicMock, socket: FakeSocket
) -> None:
    socket.connect_error = BrevilleAuthError("expired")
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="Salesforce|1",
        data={"email": "me@example.com", "id_token": make_jwt(), "refresh_token": "r"},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await flush(hass)
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]
    await hass.config_entries.async_unload(entry.entry_id)


async def test_diagnostics_have_no_personal_information(
    hass: HomeAssistant, entry: MockConfigEntry, socket: FakeSocket, client: MagicMock
) -> None:
    await push(hass, socket, csj(
        "ACTIVE", 3, timeRemaining=100, macAddress="A4:CF:12:34:56:78",
        circulatorAddress="0123456789abcdef", customerId="C-123456",
        wifi={"ssid": "Home Network", "wifiMac": "a4cf12345679", "localIp": "192.168.1.20", "rssi": -60},
        note="Set up by Pat Example (pat@example.org) on Countertop, a4:cf:12:34:56:79",
    ))
    client.recent_requests = [
        {"method": "POST", "endpoint": "update-cook", "status": 200,
         "body": {"model": "BOV950", "uuid": "c-9", "note": "Kitchen Oven"}},
        {"method": "GET", "endpoint": "appliances",
         "error": "InvalidURL('https://iot-api.breville.com/user/v2/user/Salesforce|0051234/appliances')"},
        {"method": "POST", "endpoint": "finish-wait", "status": 200,
         "body": {"applianceModel": "CSJ100"}, "response": {JOULE: {"owner": "patex"}}},
    ]
    diag = await async_get_config_entry_diagnostics(hass, entry)

    # Nothing personal anywhere in the file, inside other text or keys either.
    downloaded = json.dumps(diag, cls=ExtendedJSONEncoder).casefold()
    for personal in (
        *PROFILE.values(), "Salesforce|0051234", "Salesforce|1", "pat@example.org",
        JOULE, OVEN, "Countertop", "Kitchen Oven", "A4:CF:12:34:56:78", "a4:cf:12:34:56:79",
        "a4cf12345679", "0123456789abcdef", "Home Network", "192.168.1.20",
    ):
        assert personal.casefold() not in downloaded, personal
    assert diag["entry"]["refresh_token"] == REDACTED
    # What's needed to debug an appliance is kept.
    joule = diag["appliances"][0]
    assert (joule["model"], joule["tested"]) == ("CSJ100", True)
    data = joule["recent_messages"][-1]["message"]["data"]
    assert (data["bathTemp"], data["firmwareVersion"], data["wifi"]["rssi"]) == (55.1, "123", -60)
    assert (data["guideId"], data["cookId"]) == ("manual_x", REDACTED)
    assert diag["recent_requests"][0]["body"]["model"] == "BOV950"
    assert diag["appliances"][1]["tested"] is False
    await hass.config_entries.async_unload(entry.entry_id)


async def test_start_cook_service_options(
    hass: HomeAssistant, entry: MockConfigEntry, socket: FakeSocket, client: MagicMock
) -> None:
    hass.config_entries.async_update_entry(entry, options={CONF_ALLOW_UNTESTED_CONTROL: True})
    await push(hass, socket, OVEN_IDLE, csj("IDLE", 0, setPoint=None, cookId=None))

    def cook_phase() -> dict:
        steps = client.load_manual_recipe.await_args.args[3]
        return next(p for s in steps if s["stepType"] == "default" for p in s["phases"] if p.get("seconds"))

    await call(hass, DOMAIN, "start_cook", "switch.kitchen_oven_cook", mode="broil", level="high")
    assert (cook_phase()["mode"], cook_phase()["level"]) == (OVEN_MODES["broil"].cms, 3)
    await call(hass, DOMAIN, "start_cook", "switch.kitchen_oven_cook", mode="air_fry", convection="super")
    assert cook_phase()["convection"] == "super"

    with pytest.raises(ServiceValidationError) as err:
        await call(hass, DOMAIN, "start_cook", "switch.kitchen_oven_cook", mode="bake", level="high")
    assert err.value.translation_key == "level_not_for_mode"
    with pytest.raises(ServiceValidationError) as err:
        await call(hass, DOMAIN, "start_cook", "switch.countertop_cook", mode="bake")
    assert err.value.translation_key == "mode_oven_only"

    await call(hass, DOMAIN, "start_cook", "switch.countertop_cook", temperature=60, auto_start_timer=True)
    assert client.load_manual_recipe.await_args.args[3][0]["defaultAutostart"] is True
    await hass.config_entries.async_unload(entry.entry_id)


async def test_start_timer_automatically_switch(
    hass: HomeAssistant, entry: MockConfigEntry, socket: FakeSocket, client: MagicMock
) -> None:
    await push(hass, socket, csj("IDLE", 0, setPoint=None, cookId=None))
    for state, expected in ((STATE_ON, True), (STATE_OFF, False)):
        service = "turn_on" if state == STATE_ON else "turn_off"
        await call(hass, "switch", service, "switch.countertop_start_timer_automatically")
        assert hass.states.get("switch.countertop_start_timer_automatically").state == state
        await call(hass, "switch", "turn_on", "switch.countertop_cook")
        assert client.load_manual_recipe.await_args.args[3][0]["defaultAutostart"] is expected
    await hass.config_entries.async_unload(entry.entry_id)


async def test_websocket_reconnects(
    hass: HomeAssistant, client: MagicMock, socket: FakeSocket
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="Salesforce|1",
        data={"email": "me@example.com", "id_token": make_jwt(), "refresh_token": "r"},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.breville_cooking.coordinator.WS_RECONNECT_MIN", 0.01):
        await hass.config_entries.async_setup(entry.entry_id)
        await push(hass, socket, csj("IDLE", 0, setPoint=None, cookId=None))
        assert hass.states.get("sensor.countertop_status").state == "idle"

        await push(hass, socket, None)  # the cloud closes the connection
        for _ in range(20):
            await asyncio.sleep(0.01)
        await flush(hass)
        # Reconnected and subscribed again, with the last state kept.
        assert socket.connected and len(socket.subscribed) == 4
        assert hass.states.get("sensor.countertop_status").state == "idle"
        await hass.config_entries.async_unload(entry.entry_id)


async def test_appliance_list_errors(
    hass: HomeAssistant, entry: MockConfigEntry, socket: FakeSocket, client: MagicMock
) -> None:
    from custom_components.breville_cooking.api import BrevilleError

    await push(hass, socket, csj("IDLE", 0, setPoint=None, cookId=None))
    coordinator = entry.runtime_data
    client.get_appliances.side_effect = BrevilleError("down")
    await coordinator.async_refresh()
    await flush(hass)
    # A failed refresh alone doesn't make the appliance unavailable.
    assert not coordinator.last_update_success
    assert hass.states.get("switch.countertop_cook").state == STATE_OFF

    client.get_appliances.side_effect = BrevilleAuthError("expired")
    await coordinator.async_refresh()
    await flush(hass)
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]
    await hass.config_entries.async_unload(entry.entry_id)
