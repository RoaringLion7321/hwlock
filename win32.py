"""Thin ctypes bindings for the Win32 APIs hwlock needs."""
import ctypes
import uuid
from ctypes import wintypes as wt

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")
cfgmgr32 = ctypes.WinDLL("cfgmgr32")

LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_size_t

# --- constants -------------------------------------------------------------
WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
WM_TIMER = 0x0113
WM_QUIT = 0x0012
LLKHF_INJECTED = 0x10
LLKHF_ALTDOWN = 0x20

VK_TAB, VK_SHIFT, VK_CONTROL, VK_MENU, VK_ESCAPE = 0x09, 0x10, 0x11, 0x12, 0x1B
VK_LWIN, VK_RWIN, VK_APPS = 0x5B, 0x5C, 0x5D
VK_F11, VK_F12 = 0x7A, 0x7B
KEYEVENTF_KEYUP = 0x0002

SW_RESTORE = 9
GW_OWNER = 4
DWMWA_CLOAKED = 14
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

RIM_TYPEMOUSE, RIM_TYPEKEYBOARD, RIM_TYPEHID = 0, 1, 2
RIDI_DEVICENAME = 0x20000007

CR_SUCCESS = 0
CR_BUFFER_SMALL = 0x1A
DEVPROP_TYPE_STRING = 0x12

# --- structures ------------------------------------------------------------
class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class RAWINPUTDEVICELIST(ctypes.Structure):
    _fields_ = [("hDevice", wt.HANDLE), ("dwType", wt.DWORD)]


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD),
                ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def from_str(cls, s):
        return cls.from_buffer_copy(uuid.UUID(s).bytes_le)


class DEVPROPKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", wt.ULONG)]


def devpropkey(guid, pid):
    return DEVPROPKEY(GUID.from_str(guid), pid)


DEVPKEY_Device_DeviceDesc = devpropkey("a45c254e-df1c-4efd-8020-67d146a850e0", 2)
DEVPKEY_Device_Manufacturer = devpropkey("a45c254e-df1c-4efd-8020-67d146a850e0", 13)
DEVPKEY_Device_FriendlyName = devpropkey("a45c254e-df1c-4efd-8020-67d146a850e0", 14)
DEVPKEY_Device_BusReportedDeviceDesc = devpropkey("540b947e-8b40-45bc-a8a2-6a0b894cbda2", 4)

# --- function prototypes ---------------------------------------------------
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wt.WPARAM, wt.LPARAM)
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def _proto(dll, name, restype, *argtypes):
    fn = getattr(dll, name)
    fn.restype = restype
    fn.argtypes = argtypes
    return fn


SetWindowsHookExW = _proto(user32, "SetWindowsHookExW", wt.HHOOK, ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD)
UnhookWindowsHookEx = _proto(user32, "UnhookWindowsHookEx", wt.BOOL, wt.HHOOK)
CallNextHookEx = _proto(user32, "CallNextHookEx", LRESULT, wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM)
GetMessageW = _proto(user32, "GetMessageW", wt.BOOL, ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT)
TranslateMessage = _proto(user32, "TranslateMessage", wt.BOOL, ctypes.POINTER(wt.MSG))
DispatchMessageW = _proto(user32, "DispatchMessageW", LRESULT, ctypes.POINTER(wt.MSG))
PostThreadMessageW = _proto(user32, "PostThreadMessageW", wt.BOOL, wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM)
PostQuitMessage = _proto(user32, "PostQuitMessage", None, ctypes.c_int)
SetTimer = _proto(user32, "SetTimer", ULONG_PTR, wt.HWND, ULONG_PTR, wt.UINT, ctypes.c_void_p)
KillTimer = _proto(user32, "KillTimer", wt.BOOL, wt.HWND, ULONG_PTR)
GetAsyncKeyState = _proto(user32, "GetAsyncKeyState", wt.SHORT, ctypes.c_int)
keybd_event = _proto(user32, "keybd_event", None, wt.BYTE, wt.BYTE, wt.DWORD, ULONG_PTR)

EnumWindows = _proto(user32, "EnumWindows", wt.BOOL, WNDENUMPROC, wt.LPARAM)
IsWindow = _proto(user32, "IsWindow", wt.BOOL, wt.HWND)
IsWindowVisible = _proto(user32, "IsWindowVisible", wt.BOOL, wt.HWND)
IsIconic = _proto(user32, "IsIconic", wt.BOOL, wt.HWND)
GetWindow = _proto(user32, "GetWindow", wt.HWND, wt.HWND, wt.UINT)
GetWindowTextLengthW = _proto(user32, "GetWindowTextLengthW", ctypes.c_int, wt.HWND)
GetWindowTextW = _proto(user32, "GetWindowTextW", ctypes.c_int, wt.HWND, wt.LPWSTR, ctypes.c_int)
GetWindowThreadProcessId = _proto(user32, "GetWindowThreadProcessId", wt.DWORD, wt.HWND, ctypes.POINTER(wt.DWORD))
GetClassNameW = _proto(user32, "GetClassNameW", ctypes.c_int, wt.HWND, wt.LPWSTR, ctypes.c_int)
GetForegroundWindow = _proto(user32, "GetForegroundWindow", wt.HWND)
SetForegroundWindow = _proto(user32, "SetForegroundWindow", wt.BOOL, wt.HWND)
BringWindowToTop = _proto(user32, "BringWindowToTop", wt.BOOL, wt.HWND)
ShowWindow = _proto(user32, "ShowWindow", wt.BOOL, wt.HWND, ctypes.c_int)
AttachThreadInput = _proto(user32, "AttachThreadInput", wt.BOOL, wt.DWORD, wt.DWORD, wt.BOOL)
GetClientRect = _proto(user32, "GetClientRect", wt.BOOL, wt.HWND, ctypes.POINTER(wt.RECT))
GetWindowRect = _proto(user32, "GetWindowRect", wt.BOOL, wt.HWND, ctypes.POINTER(wt.RECT))
ClientToScreen = _proto(user32, "ClientToScreen", wt.BOOL, wt.HWND, ctypes.POINTER(wt.POINT))
ClipCursor = _proto(user32, "ClipCursor", wt.BOOL, ctypes.POINTER(wt.RECT))

GetRawInputDeviceList = _proto(user32, "GetRawInputDeviceList", wt.UINT,
                               ctypes.POINTER(RAWINPUTDEVICELIST), ctypes.POINTER(wt.UINT), wt.UINT)
GetRawInputDeviceInfoW = _proto(user32, "GetRawInputDeviceInfoW", wt.UINT,
                                wt.HANDLE, wt.UINT, ctypes.c_void_p, ctypes.POINTER(wt.UINT))

GetModuleHandleW = _proto(kernel32, "GetModuleHandleW", wt.HMODULE, wt.LPCWSTR)
GetCurrentThreadId = _proto(kernel32, "GetCurrentThreadId", wt.DWORD)
OpenProcess = _proto(kernel32, "OpenProcess", wt.HANDLE, wt.DWORD, wt.BOOL, wt.DWORD)
CloseHandle = _proto(kernel32, "CloseHandle", wt.BOOL, wt.HANDLE)
QueryFullProcessImageNameW = _proto(kernel32, "QueryFullProcessImageNameW", wt.BOOL,
                                    wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD))

DwmGetWindowAttribute = _proto(dwmapi, "DwmGetWindowAttribute", ctypes.c_long,
                               wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD)

CM_Locate_DevNodeW = _proto(cfgmgr32, "CM_Locate_DevNodeW", wt.DWORD, ctypes.POINTER(wt.DWORD), wt.LPCWSTR, wt.ULONG)
CM_Get_Device_IDW = _proto(cfgmgr32, "CM_Get_Device_IDW", wt.DWORD, wt.DWORD, wt.LPWSTR, wt.ULONG, wt.ULONG)
CM_Get_Parent =_proto(cfgmgr32, "CM_Get_Parent", wt.DWORD, ctypes.POINTER(wt.DWORD), wt.DWORD, wt.ULONG)
CM_Get_DevNode_PropertyW = _proto(cfgmgr32, "CM_Get_DevNode_PropertyW", wt.DWORD,
                                  wt.DWORD, ctypes.POINTER(DEVPROPKEY), ctypes.POINTER(wt.ULONG),
                                  ctypes.c_void_p, ctypes.POINTER(wt.ULONG), wt.ULONG)


def enable_dpi_awareness():
    """Make window/cursor coordinates physical pixels so mouse clipping lines up."""
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
    except (AttributeError, OSError):
        pass


def key_down(vk):
    return bool(GetAsyncKeyState(vk) & 0x8000)
