"""Enumerate connected keyboards, mice and other HID devices."""
import ctypes
import re
from dataclasses import dataclass
from ctypes import wintypes as wt

import win32 as w

TYPE_NAMES = {w.RIM_TYPEMOUSE: "mouse", w.RIM_TYPEKEYBOARD: "keyboard", w.RIM_TYPEHID: "hid"}


@dataclass
class Device:
    kind: str
    name: str
    manufacturer: str
    connection: str
    vid: str
    pid: str
    instance_id: str
    path: str
    handle: int


def _device_path(handle):
    size = wt.UINT(0)
    w.GetRawInputDeviceInfoW(handle, w.RIDI_DEVICENAME, None, ctypes.byref(size))
    buf = ctypes.create_unicode_buffer(size.value + 1)
    w.GetRawInputDeviceInfoW(handle, w.RIDI_DEVICENAME, buf, ctypes.byref(size))
    return buf.value


def _instance_id(path):
    # \\?\HID#VID_046D&PID_C52B&MI_00#7&2a1b&0&0000#{guid}  ->  HID\VID_046D&PID_C52B&MI_00\7&2a1b&0&0000
    p = path[4:] if path.startswith("\\\\?\\") else path
    parts = p.split("#")
    return "\\".join(parts[:3]) if len(parts) >= 3 else p


def _prop(devinst, key):
    ptype, size = wt.ULONG(0), wt.ULONG(0)
    cr = w.CM_Get_DevNode_PropertyW(devinst, ctypes.byref(key), ctypes.byref(ptype), None, ctypes.byref(size), 0)
    if cr != w.CR_BUFFER_SMALL or size.value == 0:
        return None
    buf = ctypes.create_string_buffer(size.value)
    cr = w.CM_Get_DevNode_PropertyW(devinst, ctypes.byref(key), ctypes.byref(ptype), buf, ctypes.byref(size), 0)
    if cr != w.CR_SUCCESS or ptype.value != w.DEVPROP_TYPE_STRING:
        return None
    return ctypes.wstring_at(ctypes.addressof(buf)) or None


def _node_id(devinst):
    buf = ctypes.create_unicode_buffer(512)
    if w.CM_Get_Device_IDW(devinst, buf, len(buf), 0) != w.CR_SUCCESS:
        return ""
    return buf.value.upper()


def _connection(node_ids):
    for nid in node_ids:
        if nid.startswith("USB"):
            return "usb"
        if nid.startswith("BTH") or "BLUETOOTH" in nid:
            return "bluetooth"
    if node_ids and node_ids[0].startswith(("ROOT\\", "SWD\\")) or any("CONVERTEDDEVICE" in n for n in node_ids):
        return "virtual"
    return "built-in"


def _describe(instance_id):
    """Return (name, manufacturer, connection). Walks up through HID/USB/Bluetooth
    parent nodes for the product name the device itself reports (e.g. "G915 Keyboard"
    instead of the generic "HID Keyboard Device")."""
    devinst = wt.DWORD(0)
    if w.CM_Locate_DevNodeW(ctypes.byref(devinst), instance_id, 0) != w.CR_SUCCESS:
        return None, None, "?"
    generic = _prop(devinst.value, w.DEVPKEY_Device_FriendlyName) or _prop(devinst.value, w.DEVPKEY_Device_DeviceDesc)
    manufacturer = _prop(devinst.value, w.DEVPKEY_Device_Manufacturer)

    node, chain, bus_name = devinst.value, [], None
    for _ in range(5):
        nid = _node_id(node)
        chain.append(nid)
        # Only trust names reported by peripheral buses; ACPI/PCI parents just say "PCI Device".
        if not bus_name and nid.startswith(("HID\\", "USB", "BTH")):
            bus_name = _prop(node, w.DEVPKEY_Device_BusReportedDeviceDesc)
        parent = wt.DWORD(0)
        if w.CM_Get_Parent(ctypes.byref(parent), node, 0) != w.CR_SUCCESS:
            break
        node = parent.value
    return bus_name or generic, manufacturer, _connection(chain)


def list_devices(include_hid=False):
    count = wt.UINT(0)
    size = ctypes.sizeof(w.RAWINPUTDEVICELIST)
    w.GetRawInputDeviceList(None, ctypes.byref(count), size)
    arr = (w.RAWINPUTDEVICELIST * count.value)()
    n = w.GetRawInputDeviceList(arr, ctypes.byref(count), size)
    if n == 0xFFFFFFFF:
        raise ctypes.WinError(ctypes.get_last_error())

    devices = []
    for entry in arr[:n]:
        if entry.dwType not in TYPE_NAMES or (entry.dwType == w.RIM_TYPEHID and not include_hid):
            continue
        path = _device_path(entry.hDevice)
        inst = _instance_id(path)
        name, manufacturer, connection = _describe(inst)
        vid = re.search(r"VID_([0-9A-F]{4})", path, re.I)
        pid = re.search(r"PID_([0-9A-F]{4})", path, re.I)
        devices.append(Device(
            kind=TYPE_NAMES[entry.dwType],
            name=name or "(unknown)",
            manufacturer=manufacturer or "",
            connection=connection,
            vid=vid.group(1).upper() if vid else "",
            pid=pid.group(1).upper() if pid else "",
            instance_id=inst,
            path=path,
            handle=entry.hDevice or 0,
        ))
    order = {"keyboard": 0, "mouse": 1, "hid": 2}
    devices.sort(key=lambda d: (order.get(d.kind, 9), d.name.lower()))
    return devices
