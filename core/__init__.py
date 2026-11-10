"""hwlock core engine - input devices, focus lock, notes mode, and window enumeration."""
from core.devices import Device, list_devices
from core.lock import FocusLock, BLOCKABLE, DEFAULT_BLOCK
from core.notes import NotesMode, find_text_box
from core.windows import AppWindow, list_windows, find_window, window_pid

try:
    from core.tray import Tray
except ImportError:
    Tray = None

__version__ = "0.1.0"

__all__ = [
    "Device",
    "list_devices",
    "FocusLock",
    "BLOCKABLE",
    "DEFAULT_BLOCK",
    "NotesMode",
    "find_text_box",
    "AppWindow",
    "list_windows",
    "find_window",
    "window_pid",
    "Tray",
]
