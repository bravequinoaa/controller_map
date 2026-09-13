from devices.base import normalize_hid_path


def test_normalize_hid_path_ignores_trailing_guid_and_kbd_suffix():
    hidapi_path = (
        r"\\?\HID#VID_3553&PID_B001&MI_00&Col01#8&2ddf4612&0&0000"
        r"#{4d1e55b2-f16f-11cf-88cb-001111000030}\KBD"
    )
    raw_input_path = (
        r"\\?\HID#VID_3553&PID_B001&MI_00&Col01#8&2ddf4612&0&0000"
        r"#{884b96c3-56ef-11d1-bc8c-00a0c91405dd}"
    )
    assert normalize_hid_path(hidapi_path) == normalize_hid_path(raw_input_path)


def test_normalize_hid_path_distinguishes_different_interfaces():
    col01 = r"\\?\HID#VID_3553&PID_B001&MI_00&Col01#8&2ddf4612&0&0000#{guid}\KBD"
    col03 = r"\\?\HID#VID_3553&PID_B001&MI_00&Col03#8&2ddf4612&0&0002#{guid}"
    assert normalize_hid_path(col01) != normalize_hid_path(col03)
