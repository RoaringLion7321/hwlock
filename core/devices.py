"""Enumerate connected keyboards, mice and other HID devices."""
import ctypes
import re
import uuid
from dataclasses import dataclass, field
from ctypes import wintypes as wt

from core import win32 as w

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
    container: str = ""   # Windows container ID: shared by every interface of one physical device
    boot: str = ""        # "keyboard"/"mouse" if the USB interface declares a HID boot protocol
    # every Raw Input entry merged into this one (one physical device exposes several)
    interfaces: list = field(default_factory=list)


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


def _raw_prop(devinst, key):
    """Return (type, bytes) of a device property, or (None, None)."""
    ptype, size = wt.ULONG(0), wt.ULONG(0)
    cr = w.CM_Get_DevNode_PropertyW(devinst, ctypes.byref(key), ctypes.byref(ptype), None, ctypes.byref(size), 0)
    if cr != w.CR_BUFFER_SMALL or size.value == 0:
        return None, None
    buf = ctypes.create_string_buffer(size.value)
    cr = w.CM_Get_DevNode_PropertyW(devinst, ctypes.byref(key), ctypes.byref(ptype), buf, ctypes.byref(size), 0)
    if cr != w.CR_SUCCESS:
        return None, None
    return ptype.value, buf.raw[:size.value]


def _prop(devinst, key):
    ptype, data = _raw_prop(devinst, key)
    if ptype != w.DEVPROP_TYPE_STRING:
        return None
    return data.decode("utf-16-le").split("\0", 1)[0] or None


def _prop_list(devinst, key):
    ptype, data = _raw_prop(devinst, key)
    if ptype != w.DEVPROP_TYPE_STRING_LIST:
        return []
    return [x for x in data.decode("utf-16-le").split("\0") if x]


# Placeholder container Windows gives devices with no physical container (e.g. ROOT\ virtual devices).
NULL_CONTAINER = "00000000-0000-0000-ffff-ffffffffffff"


def _container(devinst):
    ptype, data = _raw_prop(devinst, w.DEVPKEY_Device_ContainerId)
    if ptype != w.DEVPROP_TYPE_GUID or len(data) != 16:
        return ""
    cid = str(uuid.UUID(bytes_le=data))
    return "" if cid == NULL_CONTAINER else cid


def _boot_protocol(devinst):
    """USB HID interfaces declare Prot_01 (boot keyboard) or Prot_02 (boot mouse): the
    device's real job. Extra collections (a mouse's macro "keyboard", a keyboard's
    media-key "mouse") live on Prot_00 interfaces or share the boot one."""
    for cid in _prop_list(devinst, w.DEVPKEY_Device_CompatibleIds):
        m = re.search(r"Class_03&SubClass_01&Prot_0([12])", cid, re.I)
        if m:
            return "keyboard" if m.group(1) == "1" else "mouse"
    return ""


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
    """Return (name, manufacturer, connection, container, boot). Walks up through
    HID/USB/Bluetooth parent nodes for the product name the device itself reports
    (e.g. "G915 Keyboard" instead of the generic "HID Keyboard Device") and for the
    USB interface's boot protocol."""
    devinst = wt.DWORD(0)
    if w.CM_Locate_DevNodeW(ctypes.byref(devinst), instance_id, 0) != w.CR_SUCCESS:
        return None, None, "?", "", ""
    generic = _prop(devinst.value, w.DEVPKEY_Device_FriendlyName) or _prop(devinst.value, w.DEVPKEY_Device_DeviceDesc)
    manufacturer = _prop(devinst.value, w.DEVPKEY_Device_Manufacturer)
    container = _container(devinst.value)

    node, chain, bus_name, boot = devinst.value, [], None, ""
    for _ in range(5):
        nid = _node_id(node)
        chain.append(nid)
        # Only trust names reported by peripheral buses; ACPI/PCI parents just say "PCI Device".
        if not bus_name and nid.startswith(("HID\\", "USB", "BTH")):
            bus_name = _prop(node, w.DEVPKEY_Device_BusReportedDeviceDesc)
        if not boot and nid.startswith("USB\\"):
            boot = _boot_protocol(node)
        parent = wt.DWORD(0)
        if w.CM_Get_Parent(ctypes.byref(parent), node, 0) != w.CR_SUCCESS:
            break
        node = parent.value
    return bus_name or generic, manufacturer, _connection(chain), container, boot


EXTERNAL = ("usb", "bluetooth")


def list_devices(include_hid=False, merge=True, external_only=True):
    """List input devices. By default only external (USB/Bluetooth) ones, with each
    physical device merged into one entry per type it really is."""
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
        name, manufacturer, connection, container, boot = _describe(inst)
        if external_only and connection not in EXTERNAL:
            continue
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
            container=container,
            boot=boot,
        ))
    order = {"keyboard": 0, "mouse": 1, "hid": 2}
    if merge:
        devices = merge_duplicates(devices)
    devices.sort(key=lambda d: (order.get(d.kind, 9), d.name.lower()))
    return devices


def merge_duplicates(devices):
    """Collapse the Raw Input entries of each physical device.

    Windows reports one entry per HID interface/collection, so a gaming mouse also
    shows up as a "keyboard" (macro buttons) and a keyboard as several "mice" (media
    keys, knobs). Entries are grouped by physical device (container ID, falling back
    to name + VID:PID). If the device's USB interfaces declare boot protocols, only
    those types are kept: a mouse stays a mouse, a combo receiver stays both.
    Otherwise one entry per type is kept. Every instance ID goes into `interfaces`."""
    groups = {}
    for d in devices:
        key = d.container or (d.name, d.vid, d.pid, d.connection)
        groups.setdefault(key, []).append(d)

    merged = []
    for entries in groups.values():
        kinds = [k for k in ("keyboard", "mouse", "hid") if any(d.kind == k for d in entries)]
        boots = {d.boot for d in entries if d.boot}
        if boots & set(kinds):
            kinds = [k for k in kinds if k in boots]
        for kind in kinds:
            same = [d for d in entries if d.kind == kind]
            # prefer the entry on the boot interface, so the name comes from the main part
            main = next((d for d in same if d.boot == kind), same[0])
            main.interfaces = [d.instance_id for d in (entries if len(kinds) == 1 else same)]
            merged.append(main)
    return merged
