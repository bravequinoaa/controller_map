"""Test doubles for the core ports. Used headless, without hardware or a GUI."""

from collections.abc import Callable

from core.events import ButtonEvent
from core.ports import InputDevice


class FakeInputDevice(InputDevice):
    """Emits a scripted sequence of ButtonEvents on demand.

    Tests (and the M0 demo script) hold a reference to the instance and call
    emit()/emit_all() to push events through whatever callback start() was
    given, rather than generating events on a background thread.
    """

    def __init__(
        self,
        device_id: str,
        name: str,
        button_ids: list[int],
        supports_grab: bool = False,
    ) -> None:
        self.device_id = device_id
        self.name = name
        self.supports_grab = supports_grab
        self._button_ids = list(button_ids)
        self._on_event: Callable[[ButtonEvent], None] | None = None
        self.started = False

    def buttons(self) -> list[int]:
        return list(self._button_ids)

    def start(self, on_event: Callable[[ButtonEvent], None]) -> None:
        self._on_event = on_event
        self.started = True

    def stop(self) -> None:
        self.started = False
        self._on_event = None

    def emit(self, event: ButtonEvent) -> None:
        if self._on_event is None:
            raise RuntimeError("FakeInputDevice.emit() called before start()")
        self._on_event(event)

    def emit_all(self, events: list[ButtonEvent]) -> None:
        for event in events:
            self.emit(event)
