"""Regression tests for the process-global Win32 resources RawInputSource
guards: RegisterClassW and RegisterRawInputDevices must each execute at
most once no matter how many subscribers share one RawInputSource
instance. See __Design Documentation/critique/pre-M2.md, Finding 1.

These mock specific user32 entry points rather than faking RawInputSource
itself, so they exercise the real ref-counting/registration code path in
devices/raw_input.py, not a stand-in for it.
"""

from unittest.mock import patch

import pytest

from devices import raw_input as raw_input_module
from devices.raw_input import RawInputSource


def test_start_raises_when_register_class_fails():
    """RegisterClassW's return value is meaningful and checkable (unlike
    RegisterRawInputDevices, see the next test): a failure here must not be
    swallowed the way it was before this fix, since start() otherwise
    reports success with no window and no WM_INPUT ever arriving.
    """
    source = RawInputSource()
    with patch.object(raw_input_module.user32, "RegisterClassW", return_value=0):
        with pytest.raises(RuntimeError):
            source.start(lambda event: None)


def test_second_subscriber_never_reaches_register_raw_input_devices():
    """The load-bearing regression test.

    SME's correction to the original critique: a second real call to
    RegisterRawInputDevices for the same usage page/usage does not reliably
    fail. It typically succeeds and silently retargets delivery to the
    newer window, going quiet on the first listener with no failed API
    call to catch. So the fix has to structurally prevent a second call
    from ever happening, and the regression test has to prove that call
    count stays at one, not merely that a failure return would be handled.
    """
    source = RawInputSource()
    on_a: list = []
    on_b: list = []

    with patch.object(raw_input_module.user32, "RegisterRawInputDevices", return_value=1) as mock_register:
        source.start(on_a.append)
        source.start(on_b.append)
        try:
            assert mock_register.call_count == 1
        finally:
            source.stop(on_b.append)
            source.stop(on_a.append)
