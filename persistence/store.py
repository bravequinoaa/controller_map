"""JsonProfileStore: versioned JSON persistence for Config (FR-7).

Deserializes the schema in design.md into Config/Profile/Binding/Trigger/
Action, converting the on-disk button_ids list to a frozenset in memory (and
back to a sorted list on save). Writes atomically (temp file + replace) so a
crash mid-save cannot corrupt the config already on disk.
"""

import json
import logging
import os
import tempfile
from pathlib import Path

from core.events import (
    Action,
    ActionType,
    Binding,
    ButtonSignature,
    Config,
    DeviceInfo,
    MatchField,
    MatchRule,
    Profile,
    Trigger,
    TriggerKind,
)
from core.ports import ProfileStore

_logger = logging.getLogger(__name__)

SUPPORTED_VERSION = 1
DEFAULT_PROFILE_ID = "base"


def _migrate(data: dict) -> dict:
    """Upgrade a loaded config dict to SUPPORTED_VERSION.

    No-op until a version 2 schema exists; each future bump adds one step
    here instead of replacing this function. Migration behavior itself is
    not exercised by tests yet (see CLAUDE.md's Testing section); this only
    gives it a place to live.
    """
    return data


def _default_config() -> Config:
    return Config(
        version=SUPPORTED_VERSION,
        default_profile_id=DEFAULT_PROFILE_ID,
        settings={},
        profiles=[Profile(id=DEFAULT_PROFILE_ID, name="Default")],
        devices=[],
    )


def _trigger_from_dict(data: dict) -> Trigger:
    return Trigger(
        kind=TriggerKind(data["kind"]),
        device_id=data["device_id"],
        button_ids=frozenset(data["button_ids"]),
    )


def _trigger_to_dict(trigger: Trigger) -> dict:
    return {
        "kind": trigger.kind.value,
        "device_id": trigger.device_id,
        "button_ids": sorted(trigger.button_ids),
    }


def _action_from_dict(data: dict) -> Action:
    return Action(type=ActionType(data["type"]), params=data["params"])


def _action_to_dict(action: Action) -> dict:
    return {"type": action.type.value, "params": action.params}


def _binding_from_dict(data: dict) -> Binding:
    return Binding(
        trigger=_trigger_from_dict(data["trigger"]),
        actions=[_action_from_dict(a) for a in data["actions"]],
    )


def _binding_to_dict(binding: Binding) -> dict:
    return {
        "trigger": _trigger_to_dict(binding.trigger),
        "actions": [_action_to_dict(a) for a in binding.actions],
    }


def _match_rule_from_dict(data: dict) -> MatchRule:
    return MatchRule(field=MatchField(data["field"]), pattern=data["pattern"])


def _match_rule_to_dict(rule: MatchRule) -> dict:
    return {"field": rule.field.value, "pattern": rule.pattern}


def _profile_from_dict(data: dict) -> Profile:
    return Profile(
        id=data["id"],
        name=data["name"],
        chords_enabled=data.get("chords_enabled", False),
        match_rules=[_match_rule_from_dict(r) for r in data.get("match_rules", [])],
        bindings=[_binding_from_dict(b) for b in data.get("bindings", [])],
    )


def _profile_to_dict(profile: Profile) -> dict:
    return {
        "id": profile.id,
        "name": profile.name,
        "chords_enabled": profile.chords_enabled,
        "match_rules": [_match_rule_to_dict(r) for r in profile.match_rules],
        "bindings": [_binding_to_dict(b) for b in profile.bindings],
    }


def _button_signature_from_dict(data: dict) -> ButtonSignature:
    return ButtonSignature(button_id=data["button_id"], signature=data["signature"])


def _button_signature_to_dict(sig: ButtonSignature) -> dict:
    return {"button_id": sig.button_id, "signature": sig.signature}


def _device_info_from_dict(data: dict) -> DeviceInfo:
    return DeviceInfo(
        device_id=data["device_id"],
        name=data["name"],
        buttons=[_button_signature_from_dict(b) for b in data.get("buttons", [])],
    )


def _device_info_to_dict(device: DeviceInfo) -> dict:
    return {
        "device_id": device.device_id,
        "name": device.name,
        "buttons": [_button_signature_to_dict(b) for b in device.buttons],
    }


def _config_from_dict(data: dict) -> Config:
    return Config(
        version=data["version"],
        default_profile_id=data["default_profile_id"],
        settings=data.get("settings", {}),
        profiles=[_profile_from_dict(p) for p in data.get("profiles", [])],
        devices=[_device_info_from_dict(d) for d in data.get("devices", [])],
    )


def _config_to_dict(cfg: Config) -> dict:
    return {
        "version": cfg.version,
        "default_profile_id": cfg.default_profile_id,
        "settings": cfg.settings,
        "devices": [_device_info_to_dict(d) for d in cfg.devices],
        "profiles": [_profile_to_dict(p) for p in cfg.profiles],
    }


class JsonProfileStore(ProfileStore):
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load(self) -> Config:
        if not self._path.exists():
            return _default_config()

        with self._path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if data.get("version") != SUPPORTED_VERSION:
            _logger.warning(
                "config version %r is not the supported version %d; migrating",
                data.get("version"),
                SUPPORTED_VERSION,
            )
            data = _migrate(data)

        return _config_from_dict(data)

    def save(self, cfg: Config) -> None:
        data = _config_to_dict(cfg)
        self._path.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(
            dir=self._path.parent, prefix=f".{self._path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, self._path)
        except BaseException:
            os.unlink(tmp_path)
            raise
