from core.events import ButtonState
from devices.base import HidInterfaceInfo, PedalCandidate
from devices.hid_pedal import HidPedal
from devices.raw_input import RawInputEvent


class FakeRawInputSource:
    """Stands in for devices.raw_input.RawInputSource so HidPedal's edge
    detection and path filtering can be tested without real Windows Raw
    Input calls.
    """

    def __init__(self) -> None:
        self.on_event = None
        self.started = False

    def start(self, on_event) -> None:
        self.on_event = on_event
        self.started = True

    def stop(self) -> None:
        self.started = False
        self.on_event = None

    def emit(self, event: RawInputEvent) -> None:
        self.on_event(event)


PEDAL_PATH = r"\\?\HID#VID_3553&PID_B001&MI_00&Col01#8&2ddf4612&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}\KBD"
# Same physical interface as PEDAL_PATH, as Raw Input's GetRawInputDeviceInfo
# would report it (different device-interface-class GUID, no \KBD suffix).
PEDAL_PATH_VIA_RAW_INPUT = r"\\?\HID#VID_3553&PID_B001&MI_00&Col01#8&2ddf4612&0&0000#{884b96c3-56ef-11d1-bc8c-00a0c91405dd}"
OTHER_DEVICE_PATH = r"\\?\HID#VID_0000&PID_0000&MI_00#0&aaaaaaaa&0&0000#{guid}"


def make_pedal() -> tuple[HidPedal, FakeRawInputSource]:
    iface = HidInterfaceInfo(
        path=PEDAL_PATH,
        vendor_id=0x3553,
        product_id=0xB001,
        usage_page=1,
        usage=6,
        interface_number=0,
    )
    candidate = PedalCandidate(
        vendor_id=0x3553, product_id=0xB001, name="FootSwitch", manufacturer="PCsensor", interfaces=[iface]
    )
    raw = FakeRawInputSource()
    pedal = HidPedal("3553:b001#0", candidate, raw_input=raw)
    return pedal, raw


def test_learn_mode_routes_down_events_and_ignores_other_devices():
    pedal, raw = make_pedal()
    seen = []
    pedal.start_learning(seen.append)

    raw.emit(RawInputEvent(PEDAL_PATH_VIA_RAW_INPUT, "key:35", True, 1.0))
    raw.emit(RawInputEvent(PEDAL_PATH_VIA_RAW_INPUT, "key:35", False, 1.1))  # up: not a new press
    raw.emit(RawInputEvent(OTHER_DEVICE_PATH, "key:99", True, 1.2))  # not this pedal

    assert seen == ["key:35"]


def test_normal_mode_emits_button_events_on_edges_only():
    pedal, raw = make_pedal()
    pedal.load_signatures({"key:35": 1})
    events = []
    pedal.start(events.append)

    raw.emit(RawInputEvent(PEDAL_PATH_VIA_RAW_INPUT, "key:35", True, 1.0))
    raw.emit(RawInputEvent(PEDAL_PATH_VIA_RAW_INPUT, "key:35", True, 1.01))  # auto-repeat while held
    raw.emit(RawInputEvent(PEDAL_PATH_VIA_RAW_INPUT, "key:35", True, 1.02))
    raw.emit(RawInputEvent(PEDAL_PATH_VIA_RAW_INPUT, "key:35", False, 1.5))

    assert [(e.button_id, e.state) for e in events] == [
        (1, ButtonState.DOWN),
        (1, ButtonState.UP),
    ]


def test_unmapped_signature_is_ignored():
    pedal, raw = make_pedal()
    pedal.load_signatures({"key:35": 1})
    events = []
    pedal.start(events.append)

    raw.emit(RawInputEvent(PEDAL_PATH_VIA_RAW_INPUT, "key:99", True, 1.0))

    assert events == []


def test_events_from_other_devices_are_ignored_in_normal_mode():
    pedal, raw = make_pedal()
    pedal.load_signatures({"key:35": 1})
    events = []
    pedal.start(events.append)

    raw.emit(RawInputEvent(OTHER_DEVICE_PATH, "key:35", True, 1.0))

    assert events == []
