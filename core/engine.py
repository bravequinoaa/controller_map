"""Engine: wires the device, executor, and profile store together and owns
the event loop between them (FR-6).

Device reads happen on the device's own thread; per the concurrency model in
architecture.md, Engine decouples that from action execution with a queue
and its own worker thread, so a slow or blocking action (a DELAY, a launch)
never stalls the device's read loop. This is why InputDevice.start()'s
on_event callback must return fast (see core/ports.py): here, it does
nothing but a queue.put.

M2 scope only: single-profile, straight-line button presses. No
ProfileResolver app-matching and no ChordResolver merging yet (M5/M7);
every ButtonEvent maps directly to a single-button Trigger against the
default profile's bindings.
"""

import logging
import queue
import threading

from core.events import Action, ButtonEvent, ButtonState, Trigger, TriggerKind
from core.executor import ActionExecutor
from core.ports import InputDevice, OutputSink, ProfileStore

_logger = logging.getLogger(__name__)

_STOP = object()


class Engine:
    def __init__(self, device: InputDevice, sink: OutputSink, store: ProfileStore) -> None:
        self._device = device # pedal
        self._store = store # profile
        self._executor = ActionExecutor(sink)
        self._events: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._bindings: dict[Trigger, list[Action]] = {}

    def start(self) -> None:
        cfg = self._store.load()
        # next grabs the first profile with matching id and returns it
        profile = next((p for p in cfg.profiles if p.id == cfg.default_profile_id), None)
        if profile is None and cfg.profiles:
            profile = cfg.profiles[0]
        self._bindings = {b.trigger: b.actions for b in profile.bindings} if profile else {}

        self._worker = threading.Thread(target=self._run_worker, daemon=True)
        self._worker.start()
        self._device.start(self._on_device_event)

    def stop(self) -> None:
        self._device.stop()
        self._events.put(_STOP)
        if self._worker is not None:
            self._worker.join()
            self._worker = None

    def _on_device_event(self, event: ButtonEvent) -> None:
        self._events.put(event)

    def _run_worker(self) -> None:
        while True:
            item = self._events.get()
            try:
                if item is _STOP:
                    return
                self._handle_event(item)
            finally:
                self._events.task_done()

    def _handle_event(self, event: ButtonEvent) -> None:
        if event.state is not ButtonState.DOWN:
            return
        trigger = Trigger(
            kind=TriggerKind.BUTTON,
            device_id=event.device_id,
            button_ids=frozenset({event.button_id}),
        )
        actions = self._bindings.get(trigger)
        if actions is None:
            _logger.debug("no binding for trigger %r", trigger)
            return
        self._executor.execute(actions)
