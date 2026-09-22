from unittest.mock import MagicMock, patch

from pynput.keyboard import Key, KeyCode
from pynput.mouse import Button

from platform_adapters.output import PynputOutputSink, _resolve_key, _resolve_mouse_button


def test_resolve_key_named_modifier():
    assert _resolve_key("ctrl") is Key.ctrl


def test_resolve_key_is_case_insensitive():
    assert _resolve_key("CTRL") is Key.ctrl


def test_resolve_key_function_key():
    assert _resolve_key("f5") is Key.f5


def test_resolve_key_single_char_falls_back_to_keycode():
    assert _resolve_key("c") == KeyCode.from_char("c")


def test_resolve_key_unknown_multi_char_raises():
    try:
        _resolve_key("not_a_key")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_resolve_mouse_button_known():
    assert _resolve_mouse_button("left") is Button.left
    assert _resolve_mouse_button("Right") is Button.right


def test_resolve_mouse_button_unknown_raises():
    try:
        _resolve_mouse_button("scroll")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def make_sink_with_mocks() -> tuple[PynputOutputSink, MagicMock, MagicMock]:
    with patch("platform_adapters.output.KeyboardController") as kb_cls, \
         patch("platform_adapters.output.MouseController") as mouse_cls:
        kb_cls.return_value = MagicMock()
        mouse_cls.return_value = MagicMock()
        sink = PynputOutputSink()
    return sink, sink._keyboard, sink._mouse


def test_send_key_presses_in_order_and_releases_in_reverse():
    sink, keyboard, _ = make_sink_with_mocks()
    calls = []
    keyboard.press.side_effect = lambda k: calls.append(("press", k))
    keyboard.release.side_effect = lambda k: calls.append(("release", k))

    sink.send_key(["ctrl", "shift", "c"])

    assert calls == [
        ("press", Key.ctrl),
        ("press", Key.shift),
        ("press", KeyCode.from_char("c")),
        ("release", KeyCode.from_char("c")),
        ("release", Key.shift),
        ("release", Key.ctrl),
    ]


def test_send_key_releases_whatever_was_pressed_even_if_a_later_key_fails():
    sink, keyboard, _ = make_sink_with_mocks()
    calls = []

    def press(key):
        calls.append(("press", key))
        if key == Key.shift:
            raise RuntimeError("boom")

    keyboard.press.side_effect = press
    keyboard.release.side_effect = lambda k: calls.append(("release", k))

    try:
        sink.send_key(["ctrl", "shift"])
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected RuntimeError to propagate")

    assert calls == [("press", Key.ctrl), ("press", Key.shift), ("release", Key.ctrl)]


def test_send_key_unknown_key_name_raises_before_pressing_anything():
    sink, keyboard, _ = make_sink_with_mocks()

    try:
        sink.send_key(["ctrl", "not_a_key"])
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")

    keyboard.press.assert_not_called()


def test_send_mouse_clicks_resolved_button():
    sink, _, mouse = make_sink_with_mocks()
    sink.send_mouse("right")
    mouse.click.assert_called_once_with(Button.right)


def test_type_text_delegates_to_keyboard_controller():
    sink, keyboard, _ = make_sink_with_mocks()
    sink.type_text("hello")
    keyboard.type.assert_called_once_with("hello")


def test_launch_does_not_block_and_does_not_use_a_shell():
    sink, _, _ = make_sink_with_mocks()
    with patch("platform_adapters.output.subprocess.Popen") as popen:
        sink.launch("notepad.exe")
        popen.assert_called_once_with("notepad.exe")
        popen.return_value.wait.assert_not_called()
