"""ActionExecutor: runs a binding's ordered Action list against an
OutputSink, dispatching on Action.type (FR-4).
"""

import logging
import time
from collections.abc import Callable

from core.events import Action, ActionType
from core.ports import OutputSink

_logger = logging.getLogger(__name__)


class ActionExecutor:
    """Runs an ordered Action list against one OutputSink.

    An unknown action type or malformed params logs and execution moves to
    the next action rather than raising (NFR-4), so one bad step in a macro
    cannot take down the rest of it or the engine.
    """

    def __init__(self, sink: OutputSink, sleep: Callable[[float], None] = time.sleep) -> None:
        self._sink = sink
        self._sleep = sleep
        self._dispatch: dict[ActionType, Callable[[dict], None]] = {
            ActionType.KEY: self._do_key,
            ActionType.MOUSE: self._do_mouse,
            ActionType.TEXT: self._do_text,
            ActionType.LAUNCH: self._do_launch,
            ActionType.DELAY: self._do_delay,
        }

    def execute(self, actions: list[Action]) -> None:
        for action in actions:
            handler = self._dispatch.get(action.type)
            if handler is None:
                _logger.warning("unknown action type %r; skipping", action.type)
                continue
            try:
                handler(action.params)
            except Exception:
                _logger.exception(
                    "action %s failed with params %r; continuing to next action",
                    action.type,
                    action.params,
                )

    def _do_key(self, params: dict) -> None:
        self._sink.send_key(params["keys"])

    def _do_mouse(self, params: dict) -> None:
        self._sink.send_mouse(params["button"])

    def _do_text(self, params: dict) -> None:
        self._sink.type_text(params["text"])

    def _do_launch(self, params: dict) -> None:
        self._sink.launch(params["target"])

    def _do_delay(self, params: dict) -> None:
        self._sleep(params["ms"] / 1000)
