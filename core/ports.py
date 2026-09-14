"""Ports: interfaces implemented by adapters in devices/, platform/, persistence/.

Core depends on these ABCs, never on a concrete adapter. See the dependency rule
in CLAUDE.md.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable

from core.events import AppContext, ButtonEvent, Config


class InputDevice(ABC):
    device_id: str
    name: str
    supports_grab: bool

    @abstractmethod
    def buttons(self) -> list[int]: ...

    @abstractmethod
    def start(self, on_event: Callable[[ButtonEvent], None]) -> None:
        """Start delivering ButtonEvents to on_event.

        on_event may be invoked from a device-owned thread, not the
        caller's, and nothing currently queues between the device and this
        callback. Implementations and callers must treat it as something
        that has to return fast: no I/O, no blocking work. A slow on_event
        stalls the device's read loop, and for adapters that share one OS
        listener across several devices (see devices/raw_input.py), it
        stalls delivery to every device sharing that listener, not just
        this one. Handing events to a queue drained by a separate worker
        thread is Engine's responsibility (see architecture.md's
        concurrency section); on_event must not become that queue's
        consumer itself.
        """
        ...

    @abstractmethod
    def stop(self) -> None: ...

    def grab(self) -> None:  # no-op unless supports_grab
        pass

    def ungrab(self) -> None:
        pass


class OutputSink(ABC):
    @abstractmethod
    def send_key(self, keys: list[str]) -> None: ...

    @abstractmethod
    def send_mouse(self, button: str) -> None: ...

    @abstractmethod
    def type_text(self, text: str) -> None: ...

    @abstractmethod
    def launch(self, target: str) -> None: ...


class ActiveWindowWatcher(ABC):
    @abstractmethod
    def current(self) -> AppContext: ...

    def on_change(self, cb: Callable[[AppContext], None]) -> None:
        pass


class ProfileStore(ABC):
    @abstractmethod
    def load(self) -> Config: ...

    @abstractmethod
    def save(self, cfg: Config) -> None: ...
