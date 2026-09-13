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
    def start(self, on_event: Callable[[ButtonEvent], None]) -> None: ...

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
