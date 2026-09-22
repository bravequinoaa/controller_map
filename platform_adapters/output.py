"""PynputOutputSink: OutputSink adapter that synthesizes real keyboard and
mouse input and launches processes. pynput and subprocess stay confined to
this file; nothing in core imports them.
"""

import subprocess

from pynput.keyboard import Controller as KeyboardController
from pynput.keyboard import Key, KeyCode
from pynput.mouse import Button
from pynput.mouse import Controller as MouseController

from core.ports import OutputSink

_NAMED_KEYS: dict[str, Key] = {
    "ctrl": Key.ctrl,
    "control": Key.ctrl,
    "ctrl_l": Key.ctrl_l,
    "ctrl_r": Key.ctrl_r,
    "shift": Key.shift,
    "shift_l": Key.shift_l,
    "shift_r": Key.shift_r,
    "alt": Key.alt,
    "alt_l": Key.alt_l,
    "alt_r": Key.alt_r,
    "alt_gr": Key.alt_gr,
    "cmd": Key.cmd,
    "win": Key.cmd,
    "super": Key.cmd,
    "cmd_l": Key.cmd_l,
    "cmd_r": Key.cmd_r,
    "enter": Key.enter,
    "return": Key.enter,
    "esc": Key.esc,
    "escape": Key.esc,
    "tab": Key.tab,
    "space": Key.space,
    "backspace": Key.backspace,
    "delete": Key.delete,
    "del": Key.delete,
    "insert": Key.insert,
    "home": Key.home,
    "end": Key.end,
    "page_up": Key.page_up,
    "pageup": Key.page_up,
    "page_down": Key.page_down,
    "pagedown": Key.page_down,
    "up": Key.up,
    "down": Key.down,
    "left": Key.left,
    "right": Key.right,
    "caps_lock": Key.caps_lock,
    "num_lock": Key.num_lock,
    "scroll_lock": Key.scroll_lock,
    "print_screen": Key.print_screen,
    "pause": Key.pause,
    "menu": Key.menu,
}
for _n in range(1, 21):
    _f_key = getattr(Key, f"f{_n}", None)
    if _f_key is not None:
        _NAMED_KEYS[f"f{_n}"] = _f_key

_NAMED_MOUSE_BUTTONS: dict[str, Button] = {
    "left": Button.left,
    "right": Button.right,
    "middle": Button.middle,
    "x1": Button.x1,
    "x2": Button.x2,
}


def _resolve_key(name: str) -> Key | KeyCode:
    """Map a binding's key name (e.g. "ctrl", "c", "f5") to a pynput key.

    Named keys (modifiers, function keys, navigation, ...) come from
    _NAMED_KEYS; anything else must be a single printable character.
    """
    key = _NAMED_KEYS.get(name.lower())
    if key is not None:
        return key
    if len(name) == 1:
        return KeyCode.from_char(name)
    raise ValueError(f"Unknown key name: {name!r}")


def _resolve_mouse_button(name: str) -> Button:
    try:
        return _NAMED_MOUSE_BUTTONS[name.lower()]
    except KeyError:
        raise ValueError(f"Unknown mouse button: {name!r}") from None


class PynputOutputSink(OutputSink):
    def __init__(self) -> None:
        self._keyboard = KeyboardController()
        self._mouse = MouseController()

    def send_key(self, keys: list[str]) -> None:
        """Press keys in order, then release them in reverse order (a chord)."""
        resolved = [_resolve_key(name) for name in keys]
        pressed: list[Key | KeyCode] = []
        try:
            for key in resolved:
                self._keyboard.press(key)
                pressed.append(key)
        finally:
            for key in reversed(pressed):
                self._keyboard.release(key)

    def send_mouse(self, button: str) -> None:
        self._mouse.click(_resolve_mouse_button(button))

    def type_text(self, text: str) -> None:
        self._keyboard.type(text)

    def launch(self, target: str) -> None:
        """Start a process without blocking the caller."""
        subprocess.Popen(target)
