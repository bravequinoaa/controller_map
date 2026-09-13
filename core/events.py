"""Pure value objects and enums shared across the engine.

No I/O, no OS calls, no third-party imports. See CLAUDE.md for the dependency
rule: this module may only import from the standard library.
"""

from dataclasses import dataclass, field
from enum import Enum


class ButtonState(Enum):
    DOWN = "down"
    UP = "up"


class TriggerKind(Enum):
    BUTTON = "button"
    CHORD = "chord"


class ActionType(Enum):
    KEY = "key"
    MOUSE = "mouse"
    TEXT = "text"
    LAUNCH = "launch"
    DELAY = "delay"


class MatchField(Enum):
    EXE = "exe"
    TITLE = "title"
    BUNDLE_ID = "bundle_id"


class RecordMode(Enum):
    AUTO = "auto"
    EXPLICIT = "explicit"


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
    params: dict  # e.g. {"keys": ["ctrl", "c"]}, {"target": "notepad.exe"}


@dataclass
class Binding:
    trigger: Trigger
    actions: list[Action]


@dataclass
class MatchRule:
    field: MatchField
    pattern: str  # glob


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


@dataclass(frozen=True)
class ButtonSignature:
    button_id: int
    signature: str  # opaque to everything but the device adapter that produced it


@dataclass
class DeviceInfo:
    device_id: str
    name: str
    buttons: list[ButtonSignature] = field(default_factory=list)


@dataclass
class Config:
    version: int
    default_profile_id: str
    settings: dict
    profiles: list[Profile] = field(default_factory=list)
    devices: list[DeviceInfo] = field(default_factory=list)
