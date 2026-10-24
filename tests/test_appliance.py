"""Model logic: status parsing, update ordering and cook requests."""

from __future__ import annotations

from datetime import UTC, datetime
import json

import pytest

from custom_components.breville_cooking.api import StateUpdate, parse_message
from custom_components.breville_cooking.appliance import (
    MODEL_BOV950,
    MODEL_BSV600,
    MODEL_CSJ100,
    OVEN_MODES,
    CookSettings,
    CookState,
    StateTracker,
    build_bov950_steps,
    build_edit,
    build_manual_steps,
    duration_limits,
    oven_mode_defaults,
    parse_status,
    temp_mode_max_seconds,
)

NOW = datetime(2026, 10, 23, 21, 32, 11, tzinfo=UTC)
SERIAL = "J123456"


def csj_point(ts: int, state: str, step: int, remaining: int, **extra) -> dict:
    return {
        "serialNumber": SERIAL,
        "messageType": "applianceDataPoint",
        "version": str(1792805500000 + ts),
        "data": {
            "state": state, "model": "CSJ100", "programStep": step, "bathTemp": 55.1,
            "setPoint": 56.0, "cookTime": 300, "timeRemaining": remaining, "errorState": 0,
            "cookId": "fede07bad08f421d828690c7520c09ba", "guideId": "manual_x",
            "timestamp": ts, "firmwareVersion": "123", "espFirmwareVersion": "52", **extra,
        },
    }


def csj_report(version: int, ts: int, state: str, step: int, remaining: int) -> dict:
    point = csj_point(ts, state, step, remaining)
    return {
        "serialNumber": SERIAL, "messageType": "stateReport", "version": version,
        "data": {"reported": point["data"]},
    }


def feed(tracker: StateTracker, model: str, messages: list[dict]) -> dict:
    for msg in messages:
        tracker.apply(parse_message(msg), model)
    return tracker.state(SERIAL)


class TestCsj:
    def test_cooking_status(self) -> None:
        status = parse_status(MODEL_CSJ100, csj_point(1654132, "ACTIVE", 3, 300)["data"], NOW)
        assert status.state is CookState.COOKING
        assert status.cooking and status.online
        assert status.target_temp_c == 56.0
        assert status.time_remaining_s == 300
        assert status.ends_at == datetime(2026, 10, 23, 21, 37, tzinfo=UTC)

    def test_waiting_for_food_has_no_countdown(self) -> None:
        status = parse_status(MODEL_CSJ100, csj_point(1, "ACTIVE", 2, 0)["data"], NOW)
        assert status.state is CookState.READY
        assert status.time_remaining_s is None
        assert status.cook_time_s == 300

    def test_offline_and_idle(self) -> None:
        assert parse_status(MODEL_CSJ100, {"state": "OFFLINE"}).state is CookState.OFFLINE
        idle = parse_status(MODEL_CSJ100, {"state": "IDLE", "programStep": 0, "setPoint": None})
        assert idle.state is CookState.IDLE and idle.target_temp_c is None

    def test_error_reason(self) -> None:
        data = csj_point(1, "ACTIVE", 5, 0, errorState=2, eventReason=3)["data"]
        status = parse_status(MODEL_CSJ100, data)
        assert status.state is CookState.ERROR
        assert status.error == "low_water_level"

    def test_out_of_order_messages_from_capture(self) -> None:
        """The 21:32:23 Wi-Fi blip: v788 OFFLINE arrived before stale v787."""
        state = feed(StateTracker(), MODEL_CSJ100, [
            csj_point(1655132, "ACTIVE", 3, 299),
            csj_point(1664138, "OFFLINE", 3, 290),
            csj_report(788, 1664138, "OFFLINE", 3, 290),
            csj_report(787, 1655132, "ACTIVE", 3, 299),  # stale: older version
            csj_point(1664138, "ONLINE", 0, 290),
            csj_report(789, 1664138, "ONLINE", 0, 290),
            csj_point(1667192, "ACTIVE", 3, 286),
        ])
        assert state["state"] == "ACTIVE" and state["timeRemaining"] == 286

    def test_stale_point_dropped_but_reboot_accepted(self) -> None:
        tracker = StateTracker()
        feed(tracker, MODEL_CSJ100, [csj_point(1_700_000, "ACTIVE", 3, 100)])
        assert not tracker.apply(parse_message(csj_point(1_690_000, "ACTIVE", 3, 110)), MODEL_CSJ100)
        assert tracker.apply(parse_message(csj_point(5_000, "IDLE", 0, 0)), MODEL_CSJ100)
        assert tracker.state(SERIAL)["state"] == "IDLE"

    def test_edit_keeps_cook(self) -> None:
        data = csj_point(1, "ACTIVE", 3, 120)["data"]
        edit = build_edit(MODEL_CSJ100, data, parse_status(MODEL_CSJ100, data), temperature_c=58)
        assert edit.csj_program["setPoint"] == 58.0
        assert edit.csj_program["cookTime"] == 120
        assert edit.csj_program["programMetadata"]["cookId"] == data["cookId"]


OVEN_SHADOW = {
    "state": "active",
    "model": "BOV950",
    "heaters": [{"cur_temp": 150.5, "temp_sp": 205, "state": 1}],
    "timers": [{"id": 1, "state": 1, "down_from_n": 1080, "now": 900, "timestamp": 0}],
    "appliance": {"mode": 8, "frozen": 0},
    "door": {"state": 1},
    "motors": [{"state": 2}],
    "errors": [],
    "firmware": {"comm_mcu": "1.2", "host_mcu": "3.4"},
    "cookUUID": "uuid-1",
    "currentStep": 1,
}


class TestTaskEngine:
    def test_oven_status(self) -> None:
        status = parse_status(MODEL_BOV950, OVEN_SHADOW, NOW)
        assert status.state is CookState.PREHEATING
        assert status.current_temp_c == 150.5
        assert status.target_temp_c == 205
        assert status.time_remaining_s == 900 and status.cook_time_s == 1080
        assert status.mode == "air_fry"
        assert status.door_open is False
        assert status.convection == "super"
        assert status.firmware == "3.4"

    @pytest.mark.parametrize(
        ("state", "heater", "expected"),
        [
            ("active", 2, CookState.COOKING),
            ("active", 3, CookState.DONE),
            ("physicalButtonPress", 0, CookState.WAITING_FOR_BUTTON),
            ("virtualButtonPress", 2, CookState.READY),
            ("warming", 2, CookState.KEEPING_WARM),
            ("idle", 0, CookState.IDLE),
            ("offline", 0, CookState.OFFLINE),
        ],
    )
    def test_state_mapping(self, state: str, heater: int, expected: CookState) -> None:
        shadow = {**OVEN_SHADOW, "state": state, "heaters": [{"state": heater}]}
        assert parse_status(MODEL_BOV950, shadow).state is expected

    @pytest.mark.parametrize(
        ("timestamp", "expected"),
        [
            (NOW.timestamp() - 120, 780),  # sampled 2 minutes ago: 2 minutes less left
            (NOW.timestamp() - 2000, 0),  # finished since it was sampled
            (NOW.timestamp() * 1000, 900),  # milliseconds: impossible, so use `now`
        ],
    )
    def test_running_timer_corrects_for_sample_time(self, timestamp: float, expected: int) -> None:
        timer = {"id": 1, "state": 1, "down_from_n": 1080, "now": 900, "timestamp": timestamp}
        status = parse_status(MODEL_BOV950, {**OVEN_SHADOW, "timers": [timer]}, NOW)
        assert status.time_remaining_s == expected
        assert (status.ends_at is None) == (expected == 0)

    def test_skip_timer_value_means_no_timer(self) -> None:
        shadow = {**OVEN_SHADOW, "timers": [{"id": 1, "state": 1, "down_from_n": 388803, "now": 5}]}
        assert parse_status(MODEL_BOV950, shadow).time_remaining_s is None

    def test_door_error(self) -> None:
        shadow = {**OVEN_SHADOW, "errors": [{"code": 29101, "ts": 2}, {"code": 31102, "ts": 1}]}
        status = parse_status(MODEL_BOV950, shadow)
        assert status.state is CookState.ERROR and status.error == "door_open"

    def test_legacy_bsv600_fields(self) -> None:
        shadow = {"state": "active", "temperature": {"current": 54.2, "setpoint": 57},
                  "heater": {"state": 2}, "timer": {"state": 1, "down_from_n": 3600, "now": 10}}
        status = parse_status(MODEL_BSV600, shadow)
        assert (status.current_temp_c, status.target_temp_c, status.time_remaining_s) == (54.2, 57, 10)

    def test_change_report_merges_and_stale_versions_dropped(self) -> None:
        tracker = StateTracker()
        full = {"serialNumber": SERIAL, "messageType": "stateReport", "version": 10,
                "data": {"reported": OVEN_SHADOW}}
        change = {"serialNumber": SERIAL, "messageType": "changeReport", "version": 11,
                  "data": {"reported": {"heaters": [{"cur_temp": 200, "temp_sp": 205, "state": 2}]}}}
        stale = {**full, "version": 9}
        state = feed(tracker, MODEL_BOV950, [full, change, stale])
        assert state["heaters"][0]["cur_temp"] == 200
        assert state["appliance"]["mode"] == 8  # untouched by the partial update

    def test_edit_uses_update_cook(self) -> None:
        status = parse_status(MODEL_BOV950, OVEN_SHADOW)
        edit = build_edit(MODEL_BOV950, OVEN_SHADOW, status, temperature_c=210, duration_s=600)
        assert edit.uuid == "uuid-1" and edit.step == 1
        assert edit.updates == [{"name": "cookSetPoint", "value": 210}, {"name": "cookTime", "value": 600}]


class TestRequests:
    def test_bsv600_steps(self) -> None:
        (step,) = build_manual_steps(MODEL_BSV600, CookSettings(temperature_c=57.25, duration_s=5400))
        assert step["type"] == "sousVideSteps" and step["holdingTemperature"] == 57.2
        assert step["phases"] == [
            {"mode": "sousVide", "temperatureCelsius": 57.2, "seconds": 0},
            {"mode": "sousVide", "temperatureCelsius": 57.2, "seconds": 5400},
        ]
        (hold,) = build_manual_steps(MODEL_BSV600, CookSettings(temperature_c=60))
        assert hold["phases"][1] == {"mode": "sousVide", "temperatureCelsius": 60.0, "skipTimer": True, "seconds": 0}
        with pytest.raises(ValueError):
            build_manual_steps(MODEL_BSV600, CookSettings(temperature_c=95))

    def test_whole_numbers_sent_as_integers(self) -> None:
        """Like the app's JavaScript: 360, not 360.0."""
        (hold,) = build_manual_steps(MODEL_BSV600, CookSettings(temperature_c=60.0))
        assert '"temperatureCelsius": 60,' in json.dumps(hold)
        bake = oven_mode_defaults(OVEN_MODES["bake"])
        bake.temperature_c = 300.0  # clamped to the mode's 250
        steps = build_bov950_steps(bake)
        assert steps[1]["phases"][0]["temperatureCelsius"] == 250
        assert ".0" not in json.dumps(steps)
        status = parse_status(MODEL_BOV950, OVEN_SHADOW)
        edit = build_edit(MODEL_BOV950, OVEN_SHADOW, status, temperature_c=210.0)
        assert json.dumps(edit.updates) == '[{"name": "cookSetPoint", "value": 210}]'

    def test_a_bit_more_is_not_rounded(self) -> None:
        pizza = oven_mode_defaults(OVEN_MODES["pizza"])
        pizza.duration_s = 1001
        (abm,) = [s for s in build_bov950_steps(pizza) if s["stepType"] == "aBitMore"]
        assert abm["phases"][0]["seconds"] == pytest.approx(150.15)  # 0.15 x 1001, as the app

    def test_bake_preheat_then_cook(self) -> None:
        settings = oven_mode_defaults(OVEN_MODES["bake"])
        settings.temperature_c = 180
        preheat, cook, abm, keep_warm = build_bov950_steps(settings)
        phase = {"mode": "bake", "convection": "on", "rotateRemind": False,
                 "temperatureCelsius": 180, "seconds": 1800, "frozen": "off", "keepWarm": False}
        assert preheat == {
            "defaultAutostart": False, "phases": [{**phase, "seconds": 0}], "onComplete": "stayOn",
            "onCompleteTemperature": 70, "rackPosition": ["6"], "stepType": "default",
            "title": "", "type": "ovenSteps",
        }
        assert cook["phases"] == [phase] and cook["onComplete"] == "turnOff"
        assert abm["stepType"] == "aBitMore" and abm["phases"][0]["seconds"] == 360
        assert keep_warm["stepType"] == "keepWarm"
        assert keep_warm["phases"] == [{"mode": "warm", "convection": "on", "temperatureCelsius": 70, "seconds": 3600}]

    def test_air_fry_auto_start_merges_preheat(self) -> None:
        settings = oven_mode_defaults(OVEN_MODES["air_fry"])
        settings.auto_start_timer = True
        settings.keep_warm = True
        steps = build_bov950_steps(settings)
        assert [s["stepType"] for s in steps] == ["default", "aBitMore"]  # keep warm is inline
        assert steps[0]["defaultAutostart"] is True
        assert [p["seconds"] for p in steps[0]["phases"]] == [0, 1080]
        assert steps[0]["onComplete"] == "keepWarm"
        assert steps[0]["phases"][1]["convection"] == "super"

    def test_broil_level_and_limits(self) -> None:
        settings = oven_mode_defaults(OVEN_MODES["broil"])
        settings.duration_s = 3600  # over the 20 minute broil limit
        cook = build_bov950_steps(settings)[0]
        assert cook["rackPosition"] == ["1"]
        assert cook["phases"][0]["level"] == 3 and cook["phases"][0]["seconds"] == 1200
        assert "temperatureCelsius" not in cook["phases"][0]

    def test_proof_has_no_rack_or_keep_warm(self) -> None:
        steps = build_bov950_steps(oven_mode_defaults(OVEN_MODES["proof"]))
        assert [s["stepType"] for s in steps] == ["default", "aBitMore"]
        assert "rackPosition" not in steps[0]

    def test_time_limits(self) -> None:
        assert temp_mode_max_seconds(205) == 4 * 3600
        assert temp_mode_max_seconds(99) == 72 * 3600
        slow = oven_mode_defaults(OVEN_MODES["slow_cook"])
        assert slow.duration_s == 8 * 3600
        assert duration_limits(MODEL_BOV950, slow) == (4 * 3600, 72 * 3600)
        assert duration_limits(MODEL_CSJ100) == (0, 96 * 3600)

    def test_unsupported_mode(self) -> None:
        with pytest.raises(ValueError):
            build_bov950_steps(CookSettings(mode="toast"))


def test_parse_message_shapes() -> None:
    update = parse_message({"serialNumber": "s", "messageType": "changeReport", "version": "12",
                            "data": {"reported": {"a": 1}}})
    assert update == StateUpdate("s", "changeReport", {"a": 1}, False, 12)
    assert parse_message({"serialNumber": "s", "messageType": "pong", "data": {}}) is None
