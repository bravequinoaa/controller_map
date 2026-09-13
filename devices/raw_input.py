"""Windows Raw Input capture (ctypes, stdlib only, no third-party dependency).

Some HID pedals, this project's target hardware included (PCsensor FootSwitch,
VID 3553 PID B001), enumerate as a composite keyboard/mouse device. Windows'
own kbdhid.sys/mouhid.sys class drivers hold those collections exclusively:
hidapi can open them but every ReadFile fails immediately (confirmed by
probing this device). The Raw Input API is the standard way to still see
per-physical-device keyboard/mouse input: each WM_INPUT message carries the
originating device's HANDLE, which GetRawInputDeviceInfo resolves back to the
same device path hid.enumerate() reports. That lets HidPedal tell "this
keydown came from the pedal" apart from "this keydown came from the real
keyboard" without exclusive access or a global hook.

Registering for the keyboard usage page means this process receives a raw
key identifier (not typed text) for every physical keyboard's input while
running, not just the pedal's; that is inherent to how Windows lets an
application distinguish input devices; events from paths that are not the
selected pedal are discarded immediately by the caller and never inspected
further.

This module only reports raw device-path-tagged key/mouse transitions. It
does not suppress them from reaching the focused window; that is
grab/suppression, explicitly deferred (see CLAUDE.md guardrails).
"""

import ctypes
import threading
import time
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_INPUT = 0x00FF
WM_QUIT = 0x0012

RID_INPUT = 0x10000003
RIDI_DEVICENAME = 0x20000007

RIM_TYPEMOUSE = 0
RIM_TYPEKEYBOARD = 1

RIDEV_INPUTSINK = 0x00000100

HID_USAGE_PAGE_GENERIC = 0x01
HID_USAGE_GENERIC_MOUSE = 0x02
HID_USAGE_GENERIC_KEYBOARD = 0x06

RI_KEY_BREAK = 0x01  # bit set in RAWKEYBOARD.Flags means key-up

# usButtonFlags bit -> (signature, is_down)
RI_MOUSE_BUTTON_FLAGS: dict[int, tuple[str, bool]] = {
    0x0001: ("mouse:left", True),
    0x0002: ("mouse:left", False),
    0x0004: ("mouse:right", True),
    0x0008: ("mouse:right", False),
    0x0010: ("mouse:middle", True),
    0x0020: ("mouse:middle", False),
    0x0040: ("mouse:x1", True),
    0x0080: ("mouse:x1", False),
    0x0100: ("mouse:x2", True),
    0x0200: ("mouse:x2", False),
}

HWND_MESSAGE = wintypes.HWND(-3)


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [
        ("dwType", wintypes.DWORD),
        ("dwSize", wintypes.DWORD),
        ("hDevice", wintypes.HANDLE),
        ("wParam", wintypes.WPARAM),
    ]


class _RAWMOUSE_BUTTONS(ctypes.Structure):
    _fields_ = [
        ("usButtonFlags", wintypes.USHORT),
        ("usButtonData", wintypes.USHORT),
    ]


class _RAWMOUSE_UNION(ctypes.Union):
    _fields_ = [
        ("ulButtons", wintypes.ULONG),
        ("buttons", _RAWMOUSE_BUTTONS),
    ]


class RAWMOUSE(ctypes.Structure):
    _fields_ = [
        ("usFlags", wintypes.USHORT),
        ("union", _RAWMOUSE_UNION),
        ("ulRawButtons", wintypes.ULONG),
        ("lLastX", wintypes.LONG),
        ("lLastY", wintypes.LONG),
        ("ulExtraInformation", wintypes.ULONG),
    ]


class RAWKEYBOARD(ctypes.Structure):
    _fields_ = [
        ("MakeCode", wintypes.USHORT),
        ("Flags", wintypes.USHORT),
        ("Reserved", wintypes.USHORT),
        ("VKey", wintypes.USHORT),
        ("Message", wintypes.UINT),
        ("ExtraInformation", wintypes.ULONG),
    ]


class _RAWINPUT_DATA(ctypes.Union):
    _fields_ = [
        ("mouse", RAWMOUSE),
        ("keyboard", RAWKEYBOARD),
    ]


class RAWINPUT(ctypes.Structure):
    _fields_ = [
        ("header", RAWINPUTHEADER),
        ("data", _RAWINPUT_DATA),
    ]


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", wintypes.USHORT),
        ("usUsage", wintypes.USHORT),
        ("dwFlags", wintypes.DWORD),
        ("hwndTarget", wintypes.HWND),
    ]


WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


# Explicit argtypes/restype for everything called: on 64-bit Windows, HANDLEs
# and HWNDs are pointer-sized, and ctypes' default int marshaling for an
# undeclared signature can truncate them. Do not call these without argtypes.
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wintypes.ATOM

user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND

user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_long

user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = ctypes.c_int

user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.TranslateMessage.restype = wintypes.BOOL

user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.restype = ctypes.c_long

user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.restype = wintypes.BOOL

user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
user32.UnregisterClassW.restype = wintypes.BOOL

user32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT]
user32.RegisterRawInputDevices.restype = wintypes.BOOL

user32.GetRawInputData.argtypes = [
    wintypes.HANDLE, wintypes.UINT, wintypes.LPVOID, ctypes.POINTER(wintypes.UINT), wintypes.UINT,
]
user32.GetRawInputData.restype = wintypes.UINT

user32.GetRawInputDeviceInfoW.argtypes = [
    wintypes.HANDLE, wintypes.UINT, wintypes.LPVOID, ctypes.POINTER(wintypes.UINT),
]
user32.GetRawInputDeviceInfoW.restype = wintypes.UINT

user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL

kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


@dataclass(frozen=True)
class RawInputEvent:
    device_path: str
    signature: str  # e.g. "key:49" or "mouse:left"; opaque past hid_pedal.py
    is_down: bool
    timestamp: float


def _get_device_path(hDevice: int) -> str:
    size = wintypes.UINT(0)
    user32.GetRawInputDeviceInfoW(hDevice, RIDI_DEVICENAME, None, ctypes.byref(size))
    if size.value == 0:
        return ""
    buf = ctypes.create_unicode_buffer(size.value)
    user32.GetRawInputDeviceInfoW(hDevice, RIDI_DEVICENAME, buf, ctypes.byref(size))
    return buf.value


class RawInputSource:
    """Owns a hidden message-only window and pumps WM_INPUT on its own thread.

    start()/stop() may be called repeatedly (a fresh window each time).
    on_event is invoked from the listener thread; callers that touch shared
    state from it must synchronize themselves.
    """

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._ready = threading.Event()
        self._on_event: Callable[[RawInputEvent], None] | None = None
        self._wndproc_ref: WNDPROC | None = None  # keep alive so ctypes can't GC it

    def start(self, on_event: Callable[[RawInputEvent], None]) -> None:
        if self._thread is not None:
            raise RuntimeError("RawInputSource already started")
        self._on_event = on_event
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="raw-input-listener", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5.0):
            raise RuntimeError("Raw input listener window failed to start")

    def stop(self) -> None:
        if self._thread is None:
            return
        if self._thread_id is not None:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self._thread.join(timeout=5.0)
        self._thread = None
        self._thread_id = None
        self._on_event = None

    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()

        def wndproc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
            if msg == WM_INPUT:
                self._handle_input(lparam)
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc_ref = WNDPROC(wndproc)

        wndclass = WNDCLASSW()
        wndclass.style = 0
        wndclass.lpfnWndProc = self._wndproc_ref
        wndclass.hInstance = kernel32.GetModuleHandleW(None)
        wndclass.lpszClassName = "PedalControllerRawInputWindow"

        if not user32.RegisterClassW(ctypes.byref(wndclass)):
            self._ready.set()
            return

        hwnd = user32.CreateWindowExW(
            0, wndclass.lpszClassName, "PedalControllerRawInput",
            0, 0, 0, 0, 0, HWND_MESSAGE, None, wndclass.hInstance, None,
        )

        devices = (RAWINPUTDEVICE * 2)(
            RAWINPUTDEVICE(HID_USAGE_PAGE_GENERIC, HID_USAGE_GENERIC_KEYBOARD, RIDEV_INPUTSINK, hwnd),
            RAWINPUTDEVICE(HID_USAGE_PAGE_GENERIC, HID_USAGE_GENERIC_MOUSE, RIDEV_INPUTSINK, hwnd),
        )
        user32.RegisterRawInputDevices(devices, 2, ctypes.sizeof(RAWINPUTDEVICE))

        self._ready.set()

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        user32.DestroyWindow(hwnd)
        user32.UnregisterClassW(wndclass.lpszClassName, wndclass.hInstance)

    def _handle_input(self, lparam: int) -> None:
        size = wintypes.UINT(0)
        user32.GetRawInputData(lparam, RID_INPUT, None, ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
        if size.value == 0:
            return
        buf = ctypes.create_string_buffer(size.value)
        got = user32.GetRawInputData(lparam, RID_INPUT, buf, ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
        if got != size.value:
            return
        raw = ctypes.cast(buf, ctypes.POINTER(RAWINPUT)).contents

        device_path = _get_device_path(raw.header.hDevice)
        now = time.time()

        events: list[RawInputEvent] = []
        if raw.header.dwType == RIM_TYPEKEYBOARD:
            kb = raw.data.keyboard
            if kb.VKey != 0xFF:  # 0xFF marks a "no key"/overrun report, not real
                is_down = not (kb.Flags & RI_KEY_BREAK)
                events.append(RawInputEvent(device_path, f"key:{kb.VKey}", is_down, now))
        elif raw.header.dwType == RIM_TYPEMOUSE:
            flags = raw.data.mouse.union.buttons.usButtonFlags
            for bit, (signature, is_down) in RI_MOUSE_BUTTON_FLAGS.items():
                if flags & bit:
                    events.append(RawInputEvent(device_path, signature, is_down, now))

        on_event = self._on_event
        if on_event is not None:
            for event in events:
                on_event(event)
