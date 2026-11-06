"""Find application windows and the processes that own them."""
import ctypes
import os
from dataclasses import dataclass
from ctypes import wintypes as wt

import win32 as w


@dataclass
class AppWindow:
    hwnd: int
    pid: int
    exe: str
    title: str
    area: int


def window_pid(hwnd):
    pid = wt.DWORD(0)
    w.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def process_exe(pid):
    h = w.OpenProcess(w.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wt.DWORD(len(buf))
        if w.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
        return ""
    finally:
        w.CloseHandle(h)


def _is_cloaked(hwnd):
    cloaked = wt.DWORD(0)
    w.DwmGetWindowAttribute(hwnd, w.DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    return cloaked.value != 0


def _title(hwnd):
    n = w.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    w.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    w.GetClassNameW(hwnd, buf, len(buf))
    return buf.value


def list_windows():
    """Visible, top-level, titled windows (roughly what Alt+Tab shows)."""
    result = []

    @w.WNDENUMPROC
    def callback(hwnd, _):
        if (w.IsWindowVisible(hwnd) and w.GetWindowTextLengthW(hwnd) > 0
                and not w.GetWindow(hwnd, w.GW_OWNER) and not _is_cloaked(hwnd)
                and _class_name(hwnd) not in ("Progman", "WorkerW")):
            pid = window_pid(hwnd)
            r = wt.RECT()
            w.GetWindowRect(hwnd, ctypes.byref(r))
            result.append(AppWindow(hwnd, pid, process_exe(pid), _title(hwnd),
                                    max(0, r.right - r.left) * max(0, r.bottom - r.top)))
        return True

    w.EnumWindows(callback, 0)
    return result


def find_window(process=None, title=None):
    """Best match by exe name (with or without .exe) and/or title substring."""
    proc = process.lower().removesuffix(".exe") if process else None
    ttl = title.lower() if title else None
    matches = [
        win for win in list_windows()
        if (proc is None or win.exe.lower().removesuffix(".exe") == proc)
        and (ttl is None or ttl in win.title.lower())
    ]
    return max(matches, key=lambda m: m.area, default=None)
