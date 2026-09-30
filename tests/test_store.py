import json

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
from persistence.store import JsonProfileStore


def make_config() -> Config:
    return Config(
        version=1,
        default_profile_id="base",
        settings={"chord_window_ms": 40, "run_at_login": True},
        devices=[
            DeviceInfo(
                device_id="3553:b001#0",
                name="FootSwitch",
                buttons=[ButtonSignature(button_id=1, signature="key:35")],
            )
        ],
        profiles=[
            Profile(
                id="base",
                name="Default",
                chords_enabled=False,
                match_rules=[MatchRule(field=MatchField.EXE, pattern="*.exe")],
                bindings=[
                    Binding(
                        trigger=Trigger(TriggerKind.BUTTON, "3553:b001#0", frozenset({1})),
                        actions=[Action(ActionType.KEY, {"keys": ["ctrl", "c"]})],
                    ),
                    Binding(
                        trigger=Trigger(TriggerKind.CHORD, "3553:b001#0", frozenset({2, 1})),
                        actions=[Action(ActionType.LAUNCH, {"target": "notepad.exe"})],
                    ),
                ],
            )
        ],
    )


def test_missing_file_returns_a_sensible_default_config(tmp_path):
    store = JsonProfileStore(tmp_path / "config.json")

    cfg = store.load()

    assert cfg.version == 1
    assert [p.id for p in cfg.profiles] == ["base"]
    assert cfg.profiles[0].bindings == []


def test_round_trip_save_then_load_preserves_profiles_and_bindings(tmp_path):
    store = JsonProfileStore(tmp_path / "config.json")
    cfg = make_config()

    store.save(cfg)
    loaded = store.load()

    assert loaded.profiles == cfg.profiles
    assert loaded.devices == cfg.devices
    assert loaded.settings == cfg.settings
    assert loaded.default_profile_id == cfg.default_profile_id


def test_round_trip_converts_button_ids_list_to_frozenset(tmp_path):
    store = JsonProfileStore(tmp_path / "config.json")
    store.save(make_config())

    loaded = store.load()
    chord_trigger = loaded.profiles[0].bindings[1].trigger
    assert chord_trigger.button_ids == frozenset({1, 2})
    assert isinstance(chord_trigger.button_ids, frozenset)


def test_save_writes_button_ids_as_a_sorted_list_on_disk(tmp_path):
    path = tmp_path / "config.json"
    store = JsonProfileStore(path)
    cfg = make_config()

    store.save(cfg)

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["profiles"][0]["bindings"][1]["trigger"]["button_ids"] == [1, 2]


def test_save_is_atomic_and_leaves_no_temp_file_behind(tmp_path):
    store = JsonProfileStore(tmp_path / "config.json")

    store.save(make_config())

    assert list(tmp_path.iterdir()) == [tmp_path / "config.json"]


def test_a_second_store_reading_the_same_path_sees_the_same_config(tmp_path):
    path = tmp_path / "config.json"
    JsonProfileStore(path).save(make_config())

    loaded = JsonProfileStore(path).load()

    assert loaded.profiles == make_config().profiles
