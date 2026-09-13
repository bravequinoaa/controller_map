# Claude Code Brief

Paste this as the initial instruction for the project, or keep it as `CLAUDE.md`
at the repo root. Companion docs: `architecture.md` (class model, pipeline),
`design.md` (requirements with FR/NFR ids). Follow those; this brief tells you how
to build against them and in what order.

## Mission

Build a headless, event-driven engine that reads a HID foot pedal, maps button
presses (and later chords) to keyboard/mouse/launch actions, with per-application
profiles. A Tkinter tray app is a thin client of the engine. Windows first, but
written so other platforms are added as adapters, not rewrites.

## Stack and hard constraints

- Python 3.11+.
- Standard-library `tkinter` for GUI. No other GUI framework.
- Dependencies: `hidapi` (device reads), `pynput` (output synthesis and input
  capture during recording), `pywin32` (active window on Windows). JSON via the
  standard library.
- Packaged later with Nuitka. Do not add dependencies that fight native
  compilation without flagging it first.
- No `async` event loop. Use threads plus queues (see the concurrency section in
  `architecture.md`).

## The dependency rule (do not violate)

`core/` imports only from `core/` and the standard library. It must not import
from `devices/`, `platform/`, `persistence/`, or `gui/`. Those depend on `core`,
never the reverse. OS-specific and hardware-specific code lives only in `devices/`
and `platform/`, behind the interfaces defined in `core`. If you find yourself
importing `pynput`, `hidapi`, or `win32*` inside `core`, stop and move it behind a
port.

## Repo layout and per-file responsibility

```
core/
  events.py       # ButtonEvent, Trigger, Action, Binding, Profile, MatchRule,
                  # AppContext, Config, and the enums. Pure dataclasses.
  engine.py       # Engine: wires stages, owns the event loop, exposes the API
                  # the GUI calls (start/stop, reload, set_recording, list/select
                  # device, learn buttons, get/set bindings).
  chords.py       # ChordResolver: ButtonEvent stream -> Trigger. Timing window.
  profiles.py     # ProfileResolver (pure) + in-memory profile lookup building.
  recorder.py     # Recorder: capture-mode state machine, AUTO and EXPLICIT.
  ports.py        # ABCs: InputDevice, OutputSink, ActiveWindowWatcher,
                  # ProfileStore. (You may keep these here or in events.py; keep
                  # them in core either way.)
devices/
  base.py         # Device discovery helpers + shared HID parsing.
  hid_pedal.py    # HidPedal(InputDevice) via hidapi. Raw-HID read path + the
                  # signature matching that backs button learning.
platform/
  active_window.py # WindowsActiveWindow + NullActiveWindow (ActiveWindowWatcher).
  output.py        # PynputOutputSink(OutputSink).
persistence/
  store.py         # JsonProfileStore(ProfileStore): versioned load/save + migrate.
gui/
  tray.py          # Tray icon, profile menu, open-config, quit.
  config_window.py # Tkinter window: device select, learn buttons, edit bindings,
                   # record.
app.py             # Entry point: build adapters, inject into Engine, start tray.
tests/
  fakes.py         # FakeInputDevice, FakeOutputSink (records calls), FakeClock.
  test_*.py
```

## Contracts to implement first

Define these in `core` before writing any adapter. Signatures are the intent;
refine types as you go, but keep the shapes.

```python
# core/events.py
from dataclasses import dataclass, field
from enum import Enum

class ButtonState(Enum): DOWN = "down"; UP = "up"
class TriggerKind(Enum): BUTTON = "button"; CHORD = "chord"
class ActionType(Enum): KEY="key"; MOUSE="mouse"; TEXT="text"; LAUNCH="launch"; DELAY="delay"
class MatchField(Enum): EXE = "exe"; TITLE = "title"; BUNDLE_ID = "bundle_id"
class RecordMode(Enum): AUTO = "auto"; EXPLICIT = "explicit"

@dataclass(frozen=True)
class ButtonEvent:
    device_id: str
    button_id: int
    state: ButtonState
    timestamp: float

@dataclass(frozen=True)
class Trigger:
    kind: TriggerKind
    device_id: str
    button_ids: frozenset[int]

@dataclass(frozen=True)
class Action:
    type: ActionType
    params: dict          # e.g. {"keys": ["ctrl","c"]}, {"target": "notepad.exe"}

@dataclass
class Binding:
    trigger: Trigger
    actions: list[Action]

@dataclass
class MatchRule:
    field: MatchField
    pattern: str          # glob

@dataclass
class Profile:
    id: str
    name: str
    chords_enabled: bool = False
    match_rules: list[MatchRule] = field(default_factory=list)
    bindings: list[Binding] = field(default_factory=list)

@dataclass(frozen=True)
class AppContext:
    exe: str | None = None
    title: str | None = None
    bundle_id: str | None = None

@dataclass
class Config:
    version: int
    default_profile_id: str
    settings: dict
    profiles: list[Profile]
    # devices metadata (selected device, learned button signatures) also lives here
```

```python
# core/ports.py
from abc import ABC, abstractmethod
from collections.abc import Callable

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
    def grab(self) -> None: ...      # no-op unless supports_grab
    def ungrab(self) -> None: ...

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
    def on_change(self, cb: Callable[[AppContext], None]) -> None: ...

class ProfileStore(ABC):
    @abstractmethod
    def load(self) -> Config: ...
    @abstractmethod
    def save(self, cfg: Config) -> None: ...
```

Purity requirement: `ProfileResolver.resolve(ctx, profiles) -> Profile` and
`binding_for(trigger, profile) -> list[Action] | None` must be pure functions with
no I/O, so they are tested with plain data.

## Build order and acceptance criteria

Work in milestones. Each ends with something runnable and tested. Do not start a
milestone before the previous one is green.

- M0 Core skeleton and the "see presses" loop (FR-3).
  - Implement `events.py`, `ports.py`, and `FakeInputDevice` (emits scripted
    `ButtonEvent`s).
  - A tiny script wires a `FakeInputDevice` to a callback that prints normalized
    events.
  - Done when scripted presses print as `ButtonEvent`s. No hardware, no GUI.

- M1 Real device and button learning (FR-1, FR-2).
  - `devices/base.py` enumerates HID devices. `hid_pedal.py` opens the selected
    device and streams raw reports.
  - Implement the learn flow: capture the report signature per pressed pedal, map
    to `button_id`, persist under the device in `Config`.
  - Done when a real pedal's three buttons print distinct, stable `ButtonEvent`s
    after a learn pass. (If no hardware yet, keep `FakeInputDevice` and mark this
    milestone blocked on the vendor:product id.)

- M2 Binding, output, and live apply (FR-4, FR-6, FR-7).
  - `PynputOutputSink`, `ActionExecutor`, `JsonProfileStore`.
  - Single-profile bindings from disk drive real keystrokes on press.
  - Done when pressing button 1 sends a bound keystroke, and the mapping survives
    a restart.

- M3 Recording (FR-5).
  - `Recorder` with AUTO and EXPLICIT modes. Engine suppresses the executor while
    recording.
  - Done when recording produces an `Action` list that, once bound, replays
    correctly, and recorded keys never fire mappings or leak to the focused app.

- M4 GUI (FR-8, plus editing surfaces for the above).
  - `tray.py` and `config_window.py`: select device, run learn, edit bindings,
    trigger recording. GUI calls only `Engine`.
  - Done when the full map/record/apply loop is usable without the console.

- M5 Profiles (FR-9, FR-10, FR-11), then M6 app-detection (FR-12 to FR-14), then
  M7 chords (FR-15 to FR-17). Each is additive and must not touch the stages it
  does not own. Chords are the `ChordResolver` only; app-detection is
  `WindowsActiveWindow` feeding `ProfileResolver`.

## Conventions

- Type hints everywhere. Value objects are frozen dataclasses; `Trigger` must be
  hashable.
- `Action` is data (type plus params). The executor dispatches on `type`. Do not
  create an `Action` subclass hierarchy.
- Fail soft at runtime: a failed action or unknown binding logs via the standard
  `logging` module and the engine continues.
- Keep OS calls out of `core`. Keep hardware parsing in `devices`.
- No em dashes in comments or docstrings.

## Testing

- `FakeInputDevice`: emits a scripted sequence of `ButtonEvent`s on demand.
- `FakeOutputSink`: records calls so tests assert what would have been sent.
- `FakeClock`: inject time into `ChordResolver` so chord-window tests are
  deterministic and do not sleep.
- Cover: chord resolver (single press passes through when disabled; two presses
  inside the window merge; a late second press does not merge), profile resolution
  (ordered rules, first match wins, default fallback), recorder stop conditions,
  and persistence round-trip plus a version migration.

## Start here

Do M0 now: `core/events.py`, `core/ports.py`, `tests/fakes.py` with
`FakeInputDevice`, and a `scratch_print.py` that prints normalized events from a
scripted device. Stop and show the output before moving on.

## Guardrails (do not)

- Do not build the GUI first. The engine must run and be testable headless before
  any Tkinter code exists.
- Do not put `hidapi`, `pynput`, or `win32*` imports in `core`.
- Do not implement device grabbing or keyboard-emulating-pedal support yet. Return
  `supports_grab = False` and defer.
- Do not implement chords or app-detection before M7 and M6. Keep them as their own
  stage and context source when you do.
