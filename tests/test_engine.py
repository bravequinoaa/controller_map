import logging

from core.engine import Engine
from core.events import (
    Action,
    ActionType,
    Binding,
    ButtonEvent,
    ButtonState,
    Config,
    Profile,
    Trigger,
    TriggerKind,
)
from persistence.store import JsonProfileStore
from tests.fakes import FakeInputDevice, FakeOutputSink

DEVICE_ID = "3553:b001#0"


def make_store_with_one_binding(tmp_path) -> JsonProfileStore:
    store = JsonProfileStore(tmp_path / "config.json")
    cfg = Config(
        version=1,
        default_profile_id="base",
        settings={},
        devices=[],
        profiles=[
            Profile(
                id="base",
                name="Default",
                bindings=[
                    Binding(
                        trigger=Trigger(TriggerKind.BUTTON, DEVICE_ID, frozenset({1})),
                        actions=[Action(ActionType.KEY, {"keys": ["ctrl", "c"]})],
                    ),
                ],
            )
        ],
    )
    store.save(cfg)
    return store


def test_pressing_a_bound_button_fires_its_action(tmp_path):
    store = make_store_with_one_binding(tmp_path)
    device = FakeInputDevice(DEVICE_ID, "FootSwitch", [1])
    sink = FakeOutputSink()
    engine = Engine(device, sink, store)

    engine.start()
    try:
        device.emit(ButtonEvent(DEVICE_ID, 1, ButtonState.DOWN, 1.0))
        engine._events.join()

        assert sink.calls == [("send_key", (["ctrl", "c"],))]
    finally:
        engine.stop()


def test_up_event_is_consumed_and_does_not_refire_the_binding(tmp_path):
    store = make_store_with_one_binding(tmp_path)
    device = FakeInputDevice(DEVICE_ID, "FootSwitch", [1])
    sink = FakeOutputSink()
    engine = Engine(device, sink, store)

    engine.start()
    try:
        device.emit(ButtonEvent(DEVICE_ID, 1, ButtonState.UP, 1.0))
        engine._events.join()

        assert sink.calls == []
    finally:
        engine.stop()


def test_trigger_with_no_binding_logs_at_debug_and_does_nothing(tmp_path, caplog):
    store = make_store_with_one_binding(tmp_path)
    device = FakeInputDevice(DEVICE_ID, "FootSwitch", [1, 2])
    sink = FakeOutputSink()
    engine = Engine(device, sink, store)

    engine.start()
    try:
        with caplog.at_level(logging.DEBUG):
            device.emit(ButtonEvent(DEVICE_ID, 2, ButtonState.DOWN, 1.0))
            engine._events.join()

        assert sink.calls == []
        assert "no binding" in caplog.text
    finally:
        engine.stop()


def test_stop_shuts_down_the_device_and_the_worker_thread(tmp_path):
    store = make_store_with_one_binding(tmp_path)
    device = FakeInputDevice(DEVICE_ID, "FootSwitch", [1])
    engine = Engine(device, FakeOutputSink(), store)

    engine.start()
    assert device.started is True

    engine.stop()

    assert device.started is False
    assert engine._worker is None


def test_mapping_survives_a_fresh_engine_pointed_at_the_same_store_path(tmp_path):
    """Story 5: two Engines built against the same JsonProfileStore path
    resolve the same bindings without any re-configuration step, standing
    in for closing and reopening the app.
    """
    path = tmp_path / "config.json"
    make_store_with_one_binding(tmp_path)  # writes to tmp_path / "config.json"

    engine_a = Engine(FakeInputDevice(DEVICE_ID, "FootSwitch", [1]), FakeOutputSink(), JsonProfileStore(path))
    engine_a.start()

    # A second Engine/store pair against the same file, as if the process restarted.
    engine_b = Engine(FakeInputDevice(DEVICE_ID, "FootSwitch", [1]), FakeOutputSink(), JsonProfileStore(path))
    engine_b.start()

    try:
        assert engine_b._bindings == engine_a._bindings
        assert engine_b._bindings != {}
    finally:
        engine_a.stop()
        engine_b.stop()
