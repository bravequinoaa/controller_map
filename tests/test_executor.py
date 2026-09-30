import logging

from core.events import Action, ActionType
from core.executor import ActionExecutor
from tests.fakes import FakeOutputSink


def make_executor() -> tuple[ActionExecutor, FakeOutputSink, list]:
    sink = FakeOutputSink()
    sleeps: list = []
    executor = ActionExecutor(sink, sleep=sleeps.append)
    return executor, sink, sleeps


def test_executes_ordered_actions_against_sink_in_order():
    executor, sink, _ = make_executor()
    actions = [
        Action(ActionType.KEY, {"keys": ["ctrl", "c"]}),
        Action(ActionType.LAUNCH, {"target": "notepad.exe"}),
    ]

    executor.execute(actions)

    assert sink.calls == [
        ("send_key", (["ctrl", "c"],)),
        ("launch", ("notepad.exe",)),
    ]


def test_mouse_and_text_actions_dispatch_to_the_right_sink_method():
    executor, sink, _ = make_executor()

    executor.execute(
        [
            Action(ActionType.MOUSE, {"button": "right"}),
            Action(ActionType.TEXT, {"text": "hello"}),
        ]
    )

    assert sink.calls == [("send_mouse", ("right",)), ("type_text", ("hello",))]


def test_delay_sleeps_seconds_derived_from_ms_without_touching_the_sink():
    executor, sink, sleeps = make_executor()

    executor.execute([Action(ActionType.DELAY, {"ms": 250})])

    assert sleeps == [0.25]
    assert sink.calls == []


def test_unknown_action_type_is_skipped_and_logged_but_later_actions_still_run(caplog):
    executor, sink, _ = make_executor()

    with caplog.at_level(logging.WARNING):
        executor.execute(
            [
                Action(type="not_a_real_type", params={}),
                Action(ActionType.TEXT, {"text": "ok"}),
            ]
        )

    assert sink.calls == [("type_text", ("ok",))]
    assert "unknown action type" in caplog.text


def test_malformed_params_logs_and_continues_to_next_action(caplog):
    executor, sink, _ = make_executor()

    with caplog.at_level(logging.ERROR):
        executor.execute(
            [
                Action(ActionType.KEY, {}),  # missing required "keys"
                Action(ActionType.TEXT, {"text": "still runs"}),
            ]
        )

    assert sink.calls == [("type_text", ("still runs",))]
    assert "action" in caplog.text.lower()


def test_a_raising_sink_does_not_stop_the_rest_of_the_binding(caplog):
    sink = FakeOutputSink()

    def failing_send_key(keys):
        raise RuntimeError("boom")

    sink.send_key = failing_send_key
    executor = ActionExecutor(sink, sleep=lambda s: None)

    with caplog.at_level(logging.ERROR):
        executor.execute(
            [
                Action(ActionType.KEY, {"keys": ["ctrl", "c"]}),
                Action(ActionType.TEXT, {"text": "after the failure"}),
            ]
        )

    assert sink.calls == [("type_text", ("after the failure",))]
