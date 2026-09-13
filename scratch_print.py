"""M0 demo: wire a FakeInputDevice to a callback that prints normalized events.

No hardware, no GUI. Run with: python scratch_print.py
"""

from core.events import ButtonEvent, ButtonState
from tests.fakes import FakeInputDevice


def on_event(event: ButtonEvent) -> None:
    print(event)


def main() -> None:
    device = FakeInputDevice(device_id="0c45:7403#0", name="Fake Foot Switch", button_ids=[1, 2, 3])
    device.start(on_event)

    script = [
        ButtonEvent(device.device_id, 1, ButtonState.DOWN, timestamp=0.000),
        ButtonEvent(device.device_id, 1, ButtonState.UP, timestamp=0.080),
        ButtonEvent(device.device_id, 2, ButtonState.DOWN, timestamp=0.500),
        ButtonEvent(device.device_id, 2, ButtonState.UP, timestamp=0.560),
        ButtonEvent(device.device_id, 3, ButtonState.DOWN, timestamp=1.000),
        ButtonEvent(device.device_id, 3, ButtonState.UP, timestamp=1.040),
    ]
    device.emit_all(script)

    device.stop()


if __name__ == "__main__":
    main()
