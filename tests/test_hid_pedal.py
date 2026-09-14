from core.events import ButtonState
from devices.base import HidInterfaceInfo, PedalCandidate
from devices.hid_pedal import HidPedal
from devices.raw_input import RawInputEvent


class FakeRawInputBus:
    """Fan-out point optionally shared by several FakeRawInputSource
    handles, mirroring how several HidPedal instances share one
    process-wide RawInputSource in production (see
    devices/raw_input.py:shared_source()).
    """

    def __init__(self) -> None:
        self.subscribers: list = []

    def subscribe(self, on_event) -> None:
        self.subscribers.append(on_event)

    def unsubscribe(self, on_event) -> None:
        if on_event in self.subscribers:
            self.subscribers.remove(on_event)

    def emit(self, event: RawInputEvent) -> None:
        for on_event in list(self.subscribers):
            on_event(event)


class FakeRawInputSource:
    """Stands in for devices.raw_input.SharedRawInputSource (a per-caller
    handle onto the shared listener) so HidPedal's edge detection and path
    filtering can be tested without real Windows Raw Input calls.

    Pass the same FakeRawInputBus to several FakeRawInputSource instances
    to prove fan-out across HidPedals; leave it unset for a private,
    single-subscriber fake (the common case for most tests here).
    """

    def __init__(self, bus: FakeRawInputBus | None = None) -> None:
        self._bus = bus if bus is not None else FakeRawInputBus()
        self.on_event = None

    @property
    def started(self) -> bool:
        return self.on_event is not None

    def start(self, on_event) -> None:
        self.on_event = on_event
        self._bus.subscribe(on_event)

    def stop(self) -> None:
        if self.on_event is not None:
            self._bus.unsubscribe(self.on_event)
            self.on_event = None

    def emit(self, event: RawInputEvent) -> None:
        self._bus.emit(event)


PEDAL_PATH = r"\\?\HID#VID_3553&PID_B001&MI_00&Col01#8&2ddf4612&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}\KBD"
# Same physical interface as PEDAL_PATH, as Raw Input's GetRawInputDeviceInfo
# would report it (different device-interface-class GUID, no \KBD suffix).
PEDAL_PATH_VIA_RAW_INPUT = r"\\?\HID#VID_3553&PID_B001&MI_00&Col01#8&2ddf4612&0&0000#{884b96c3-56ef-11d1-bc8c-00a0c91405dd}"
OTHER_DEVICE_PATH = r"\\?\HID#VID_0000&PID_0000&MI_00#0&aaaaaaaa&0&0000#{guid}"
# A second, distinct physical pedal, for the fan-out test below.
SECOND_PEDAL_PATH = r"\\?\HID#VID_3553&PID_B001&MI_00&Col01#8&1111aaaa&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}\KBD"
SECOND_PEDAL_PATH_VIA_RAW_INPUT = r"\\?\HID#VID_3553&PID_B001&MI_00&Col01#8&1111aaaa&0&0000#{884b96c3-56ef-11d1-bc8c-00a0c91405dd}"


def make_pedal(
    device_id: str = "3553:b001#0",
    path: str = PEDAL_PATH,
    bus: FakeRawInputBus | None = None,
) -> tuple[HidPedal, FakeRawInputSource]:
    iface = HidInterfaceInfo(
        path=path,
        vendor_id=0x3553,
        product_id=0xB001,
        usage_page=1,
        usage=6,
        interface_number=0,
    )
    candidate = PedalCandidate(
        vendor_id=0x3553, product_id=0xB001, name="FootSwitch", manufacturer="PCsensor", interfaces=[iface]
    )
    raw = FakeRawInputSource(bus=bus)
    pedal = HidPedal(device_id, candidate, raw_input=raw)
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


def test_two_pedals_sharing_one_listener_each_receive_only_their_own_events():
    """Mirrors devices/raw_input.py's production shape: several HidPedal
    instances share one listener (there, a process-wide RawInputSource; here,
    one FakeRawInputBus) and must each still only see their own device's
    events, with per-device edge/repeat state kept independently.
    """
    bus = FakeRawInputBus()
    pedal_a, raw_a = make_pedal(device_id="3553:b001#0", path=PEDAL_PATH, bus=bus)
    pedal_b, raw_b = make_pedal(device_id="3553:b001#1", path=SECOND_PEDAL_PATH, bus=bus)
    pedal_a.load_signatures({"key:35": 1})
    pedal_b.load_signatures({"key:35": 1})
    events_a: list = []
    events_b: list = []
    pedal_a.start(events_a.append)
    pedal_b.start(events_b.append)

    assert bus.subscribers == [pedal_a._on_raw_event, pedal_b._on_raw_event]

    raw_a.emit(RawInputEvent(PEDAL_PATH_VIA_RAW_INPUT, "key:35", True, 1.0))
    raw_a.emit(RawInputEvent(SECOND_PEDAL_PATH_VIA_RAW_INPUT, "key:35", True, 1.1))

    assert [(e.device_id, e.button_id, e.state) for e in events_a] == [
        ("3553:b001#0", 1, ButtonState.DOWN),
    ]
    assert [(e.device_id, e.button_id, e.state) for e in events_b] == [
        ("3553:b001#1", 1, ButtonState.DOWN),
    ]

    pedal_a.stop()
    assert bus.subscribers == [pedal_b._on_raw_event]  # stopping one leaves the other listening

    raw_b.emit(RawInputEvent(SECOND_PEDAL_PATH_VIA_RAW_INPUT, "key:35", False, 1.2))
    assert [(e.device_id, e.button_id, e.state) for e in events_b] == [
        ("3553:b001#1", 1, ButtonState.DOWN),
        ("3553:b001#1", 1, ButtonState.UP),
    ]
