"""M1 demo: learn the real pedal's buttons, then print normalized ButtonEvents
as they're pressed. Real hardware, no GUI.

Learning here uses a single fixed capture window and orders buttons by first
appearance, rather than HidPedal.learn_buttons' per-button prompts, because
this script's output isn't visible to the operator until it exits (no live
terminal). A GUI driving HidPedal.start_learning directly can show prompts
in real time and take turns per button instead.

Run with: python scratch_learn_and_print.py
"""

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
    candidates = [
        c for c in enumerate_candidates() if c.vendor_id == VENDOR_ID and c.product_id == PRODUCT_ID
    ]
    if not candidates:
        print(f"No device {VENDOR_ID:04x}:{PRODUCT_ID:04x} found")
        sys.exit(1)

    candidate = candidates[0]
    device_id = logical_device_id(candidate.vendor_id, candidate.product_id)
    pedal = HidPedal(device_id, candidate)

    order: list[str] = []

    def on_signature(signature: str) -> None:
        if signature not in order:
            order.append(signature)
            print(f"  saw new signature #{len(order)}: {signature}")

    print(f"Learning up to {BUTTON_COUNT} buttons on {candidate.name} ({device_id})")
    print(f"Capturing for {LEARN_SECONDS}s now.")
    pedal.start_learning(on_signature)
    time.sleep(LEARN_SECONDS)
    pedal.stop_learning()

    if len(order) < BUTTON_COUNT:
        print(f"\nOnly saw {len(order)} distinct signature(s), expected {BUTTON_COUNT}")
        sys.exit(1)

    signatures = {sig: i + 1 for i, sig in enumerate(order[:BUTTON_COUNT])}
    pedal.load_signatures(signatures)
    print("\nLearned signatures:")
    for signature, button_id in sorted(signatures.items(), key=lambda kv: kv[1]):
        print(f"  button {button_id}: {signature}")

    def on_event(event) -> None:
        print(event)

    print(f"\nVerification: press any pedal button for the next {VERIFY_SECONDS}s...\n")
    pedal.start(on_event)
    time.sleep(VERIFY_SECONDS)
    pedal.stop()
    print("\ndone")


if __name__ == "__main__":
    main()
