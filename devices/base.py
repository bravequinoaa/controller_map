"""HID device discovery and grouping.

Enumeration via hidapi works even for keyboard-emulating composite devices;
only *reading* the collections Windows' own class drivers own is blocked (see
devices/raw_input.py for why hid_pedal.py does not use hidapi reads for
those). This module only lists and groups interfaces; it does no reading.
"""

from dataclasses import dataclass, field

import hid


@dataclass(frozen=True)
class HidInterfaceInfo:
    path: str
    vendor_id: int
    product_id: int
    usage_page: int
    usage: int
    interface_number: int


@dataclass
class PedalCandidate:
    """One physical device, grouped from its (possibly several) HID interfaces.

    A composite device (e.g. keyboard + mouse + vendor interfaces sharing one
    physical product) enumerates as several hidapi entries sharing a
    vendor_id/product_id; this groups them so the user picks a device once,
    not once per interface.
    """

    vendor_id: int
    product_id: int
    name: str
    manufacturer: str
    interfaces: list[HidInterfaceInfo] = field(default_factory=list)


def enumerate_candidates() -> list[PedalCandidate]:
    """List connected HID devices, grouped by (vendor_id, product_id)."""
    grouped: dict[tuple[int, int], PedalCandidate] = {}
    for entry in hid.enumerate():
        key = (entry["vendor_id"], entry["product_id"])
        candidate = grouped.get(key)
        if candidate is None:
            candidate = PedalCandidate(
                vendor_id=entry["vendor_id"],
                product_id=entry["product_id"],
                name=entry.get("product_string") or f"{entry['vendor_id']:04x}:{entry['product_id']:04x}",
                manufacturer=entry.get("manufacturer_string") or "",
            )
            grouped[key] = candidate
        path = entry["path"]
        candidate.interfaces.append(
            HidInterfaceInfo(
                path=path.decode() if isinstance(path, bytes) else path,
                vendor_id=entry["vendor_id"],
                product_id=entry["product_id"],
                usage_page=entry.get("usage_page", 0),
                usage=entry.get("usage", 0),
                interface_number=entry.get("interface_number", -1),
            )
        )
    return list(grouped.values())


def logical_device_id(vendor_id: int, product_id: int, index: int = 0) -> str:
    """Hardware-agnostic device id per NFR-6: vendor:product plus a stable index."""
    return f"{vendor_id:04x}:{product_id:04x}#{index}"


def normalize_hid_path(path: str) -> str:
    """Collapse a HID device path to the segments that identify the physical
    interface instance, dropping the trailing device-interface-class GUID.

    Windows exposes the same underlying interface through several symbolic
    links (GUID_DEVINTERFACE_HID for hidapi, GUID_DEVINTERFACE_KEYBOARD or
    GUID_DEVINTERFACE_MOUSE for Raw Input's GetRawInputDeviceInfo), which
    differ only in that trailing GUID (and an optional \\KBD suffix). Paths
    that agree on everything up to there are the same physical interface.
    """
    segments = path.split("#")
    if len(segments) < 3:
        return path.lower()
    return "#".join(segments[1:3]).lower()
