import sys
import time

from devices.base import enumerate_candidates, logical_device_id
from devices.hid_pedal import HidPedal

VENDOR_ID = 0x3553
PRODUCT_ID = 0xB001
BUTTON_COUNT = 3
LEARN_SECONDS = 25
VERIFY_SECONDS = 15


def main() -> None:
    print('starting...')
    # find pedal candidates
    candidates = [
        c for c in enumerate_candidates() if c.vendor_id == VENDOR_ID and c.product_id == PRODUCT_ID
    ]
    if not candidates:
        print(f"No device {VENDOR_ID:04x}:{PRODUCT_ID:04x} found")
        sys.exit(1)

    candidate = candidates[0]
    device_id = logical_device_id(candidate.vendor_id, candidate.product_id)
    pedal = HidPedal(device_id, candidate)


    i_key = pedal.get__interface_keys()
    print(f'i keys type: {type(i_key)}')
    print(f'i keys: {i_key}')

    print('iter' + ': '.join(i_k for i_k in i_key))

if __name__=="__main__":
    main()