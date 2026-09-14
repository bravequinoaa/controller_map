"""HidPedal: InputDevice adapter for HID foot pedals.

Some pedals, this project's confirmed hardware included (PCsensor FootSwitch,
VID 3553 PID B001), are keyboard/mouse-emulating: they enumerate as a
composite HID device whose keyboard and mouse collections are owned
exclusively by Windows' own class drivers, so raw hidapi reads on those
collections fail. HidPedal instead uses Windows' Raw Input API
(devices/raw_input.py) to see per-physical-device key/mouse transitions and
normalizes the ones that come from this pedal's interfaces into ButtonEvents.

It does not suppress the underlying keystroke/click from also reaching the
focused window; that is grab/suppression, explicitly deferred
(supports_grab stays False per CLAUDE.md).
"""

import queue
from collections.abc import Callable

from core.events import ButtonEvent, ButtonState
from core.ports import InputDevice
from devices.base import PedalCandidate, normalize_hid_path
from devices.raw_input import RawInputEvent, RawInputListener, shared_source


class HidPedal(InputDevice):
    supports_grab = False

    def __init__(
        self,
        device_id: str,
        candidate: PedalCandidate,
        raw_input: RawInputListener | None = None,
    ) -> None:
        self.device_id = device_id
        self.name = candidate.name
        self._candidate = candidate
        self._interface_keys = {normalize_hid_path(iface.path) for iface in candidate.interfaces}
        # Several HidPedal instances share one process-wide Raw Input
        # listener (devices/raw_input.py); shared_source() hands each of
        # them its own handle onto it. Tests inject a fake here instead.
        self._raw_input = raw_input if raw_input is not None else shared_source()
        self._signatures: dict[str, int] = {}  # raw signature -> button_id
        self._button_state: dict[int, bool] = {}  # button_id -> currently down
        self._on_event: Callable[[ButtonEvent], None] | None = None
        self._learn_sink: Callable[[str], None] | None = None

    def buttons(self) -> list[int]:
        return sorted(set(self._signatures.values()))

    def load_signatures(self, signatures: dict[str, int]) -> None:
        """Install learned raw-signature -> button_id mappings (from Config)."""
        self._signatures = dict(signatures)
        self._button_state = {}

    def start(self, on_event: Callable[[ButtonEvent], None]) -> None:
        """Start streaming ButtonEvents to on_event.

        on_event is invoked from the shared raw-input listener thread (see
        devices/raw_input.py); it must return fast with no I/O or blocking
        work, since a slow callback stalls delivery to every other device
        sharing that thread, not just this one. Queueing and dispatch onto
        a worker thread is Engine's responsibility (M2), not this method's.
        """
        self._on_event = on_event
        self._raw_input.start(self._on_raw_event)

    def stop(self) -> None:
        self._raw_input.stop()
        self._on_event = None

    def start_learning(self, on_signature: Callable[[str], None]) -> None:
        """Divert raw down-events to on_signature instead of emitting
        ButtonEvents. Used by the interactive learn flow (FR-2).
        """
        self._learn_sink = on_signature
        self._raw_input.start(self._on_raw_event)

    def stop_learning(self) -> None:
        self._raw_input.stop()
        self._learn_sink = None

    def _on_raw_event(self, event: RawInputEvent) -> None:
        """Handle one RawInputEvent from the shared listener thread.

        Runs inline with every other HidPedal sharing that listener; must
        stay fast and non-blocking (see start()).
        """
        if normalize_hid_path(event.device_path) not in self._interface_keys:
            return

        if self._learn_sink is not None:
            if event.is_down:
                self._learn_sink(event.signature)
            return

        button_id = self._signatures.get(event.signature)
        if button_id is None:
            return

        was_down = self._button_state.get(button_id, False)
        if event.is_down == was_down:
            return  # auto-repeat while held; only edges become ButtonEvents
        self._button_state[button_id] = event.is_down

        on_event = self._on_event
        if on_event is not None:
            on_event(
                ButtonEvent(
                    device_id=self.device_id,
                    button_id=button_id,
                    state=ButtonState.DOWN if event.is_down else ButtonState.UP,
                    timestamp=event.timestamp,
                )
            )


def learn_buttons(
    pedal: HidPedal,
    count: int,
    on_prompt: Callable[[int], None] | None = None,
    timeout_s: float = 15.0,
) -> dict[str, int]:
    """Interactive learn flow (FR-2): capture one distinct raw signature per
    pedal button, in turn, and install the mapping on `pedal`.

    Blocks the calling thread; call from a worker thread, not the GUI thread.
    """
    signatures: dict[str, int] = {}
    inbox: queue.Queue[str] = queue.Queue()

    pedal.start_learning(inbox.put)
    try:
        for button_id in range(1, count + 1):
            if on_prompt is not None:
                on_prompt(button_id)
            while True:
                try:
                    signature = inbox.get(timeout=timeout_s)
                except queue.Empty:
                    raise TimeoutError(f"No press seen for button {button_id} within {timeout_s}s")
                if signature in signatures:
                    continue  # an already-assigned button was pressed again
                signatures[signature] = button_id
                break
    finally:
        pedal.stop_learning()

    pedal.load_signatures(signatures)
    return signatures
