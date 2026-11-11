"""Focus lock: keep keyboard (and optionally mouse) input going to one application.

Windows delivers keyboard input to the foreground window, so "locking the keyboard
to an app" means:
  1. keeping the target window in the foreground (refocusing it if something steals focus),
  2. swallowing the keys that would switch away from it (Win, Alt+Tab, ...),
  3. optionally confining the mouse cursor to the window.

Hotkeys (always active while hwlock runs):
  Ctrl+Shift+F11  pause / resume the lock
  Ctrl+Shift+F12  quit hwlock
"""
import ctypes
import time
from ctypes import wintypes as wt

from core import win32 as w
from core.windows import find_window, process_exe, window_pid, window_title

BLOCKABLE = {
    "win": "Windows keys (Start menu, Win+D, Win+Tab, ...)",
    "alttab": "Alt+Tab",
    "altesc": "Alt+Esc",
    "ctrlesc": "Ctrl+Esc (Start menu)",
    "apps": "Menu / Apps key",
}
DEFAULT_BLOCK = ("win", "alttab", "altesc", "ctrlesc")

TICK_MS = 50
REFOCUS_COOLDOWN = 0.25


class FocusLock:
    """Lock to one window.

    Give `hwnd` to lock to an exact window (the GUI does this), and/or `process` / `title`
    to find one by name. When the window closes, the lock waits and re-attaches to the best
    match for `process` / `title` (if given), e.g. when a game is restarted.
    """

    def __init__(self, process=None, title=None, hwnd=None, block=DEFAULT_BLOCK, refocus=True,
                 clip_mouse=False, exempt_pids=(), log=print):
        if not (process or title or hwnd):
            raise ValueError("need a process name, window title or window handle")
        self.process, self.title = process, title
        self.block = set(block)
        self.refocus = refocus
        self.clip_mouse = clip_mouse
        # Processes whose windows may come to the front without being pushed back
        # (the GUI passes its own pid, so its window can be used to unlock).
        self.exempt_pids = set(exempt_pids)
        self.log = log

        self.active = True
        self.hwnd = hwnd
        self.pid = window_pid(hwnd) if hwnd else None
        self._hook = None
        self._hook_proc = w.HOOKPROC(self._keyboard_proc)  # keep a reference: ctypes callbacks get GC'd
        self._swallowed = set()   # keys whose key-down we blocked, so we also block their key-up
        self._last_refocus = 0.0
        self._clipped = False
        self._thread_id = None
        self._stop_requested = False

    # ---------------------------------------------------------------- target
    def _acquire_target(self):
        """Find a window by process / title (used at start and after the target closes)."""
        if not (self.process or self.title):
            return False   # locked to a window handle only: nothing to search for
        win = find_window(self.process, self.title)
        if win:
            if win.hwnd != self.hwnd:
                self.log(f"[lock] target: {win.exe} (pid {win.pid}) \"{win.title}\"")
            self.hwnd, self.pid = win.hwnd, win.pid
        return bool(win)

    def _target_alive(self):
        return bool(self.hwnd) and w.IsWindow(self.hwnd)

    def _target_focused(self):
        """True if the target window, or a window it owns (its dialogs, message boxes), is
        in front. Other windows of the same process (e.g. a second Chrome window) don't count."""
        fg = w.GetForegroundWindow()
        return bool(fg) and (fg == self.hwnd or w.GetAncestor(fg, w.GA_ROOTOWNER) == self.hwnd)

    # -------------------------------------------------------------- keyboard
    def _keyboard_proc(self, n_code, w_param, l_param):
        if n_code == w.HC_ACTION:
            kb = ctypes.cast(l_param, ctypes.POINTER(w.KBDLLHOOKSTRUCT)).contents
            if self._handle_key(kb, w_param in (w.WM_KEYDOWN, w.WM_SYSKEYDOWN)):
                return 1
        return w.CallNextHookEx(None, n_code, w_param, l_param)

    def _handle_key(self, kb, down):
        """Return True to swallow the key event."""
        vk = kb.vkCode

        # Our own hotkeys.
        if vk in (w.VK_F11, w.VK_F12) and w.key_down(w.VK_CONTROL) and w.key_down(w.VK_SHIFT):
            if down:
                if vk == w.VK_F11:
                    self.set_active(not self.active)
                else:
                    self.log("[lock] quit hotkey pressed")
                    w.PostQuitMessage(0)
            return True

        if not down:
            if vk in self._swallowed:
                self._swallowed.discard(vk)
                return True
            return False

        if (not self.active or kb.flags & w.LLKHF_INJECTED
                or not self._target_alive() or not self._target_focused()):
            return False

        alt = bool(kb.flags & w.LLKHF_ALTDOWN)
        blocked = (
            ("win" in self.block and vk in (w.VK_LWIN, w.VK_RWIN))
            or ("alttab" in self.block and alt and vk == w.VK_TAB)
            or ("altesc" in self.block and alt and vk == w.VK_ESCAPE)
            or ("ctrlesc" in self.block and vk == w.VK_ESCAPE and w.key_down(w.VK_CONTROL))
            or ("apps" in self.block and vk == w.VK_APPS)
        )
        if blocked:
            self._swallowed.add(vk)
        return blocked

    # ----------------------------------------------------------------- focus
    def _bring_to_front(self):
        hwnd = self.hwnd
        if w.IsIconic(hwnd):
            w.ShowWindow(hwnd, w.SW_RESTORE)
        fg_thread = w.GetWindowThreadProcessId(w.GetForegroundWindow(), None)
        me = w.GetCurrentThreadId()
        attached = bool(fg_thread) and fg_thread != me and w.AttachThreadInput(me, fg_thread, True)
        try:
            ok = w.SetForegroundWindow(hwnd)
            w.BringWindowToTop(hwnd)
        finally:
            if attached:
                w.AttachThreadInput(me, fg_thread, False)
        if not ok:
            # Windows only lets the process that last received input change the
            # foreground window; a synthetic Alt tap satisfies that rule.
            w.keybd_event(w.VK_MENU, 0, 0, 0)
            w.keybd_event(w.VK_MENU, 0, w.KEYEVENTF_KEYUP, 0)
            ok = w.SetForegroundWindow(hwnd)
        return ok

    def _apply_clip(self):
        rect = wt.RECT()
        w.GetClientRect(self.hwnd, ctypes.byref(rect))
        tl, br = wt.POINT(rect.left, rect.top), wt.POINT(rect.right, rect.bottom)
        w.ClientToScreen(self.hwnd, ctypes.byref(tl))
        w.ClientToScreen(self.hwnd, ctypes.byref(br))
        screen = wt.RECT(tl.x, tl.y, br.x, br.y)
        if screen.right > screen.left and screen.bottom > screen.top:
            w.ClipCursor(ctypes.byref(screen))
            self._clipped = True

    def _release_clip(self):
        if self._clipped:
            w.ClipCursor(None)
            self._clipped = False

    def _tick(self):
        if not self._target_alive():
            had_target = self.hwnd is not None
            self.hwnd = self.pid = None
            self._release_clip()
            if not self._acquire_target():
                if had_target:
                    self.log("[lock] target window closed, waiting for it to come back...")
                return
        if not self.active:
            return

        fg = w.GetForegroundWindow()
        if self._target_focused():
            if self.clip_mouse:
                self._apply_clip()   # re-applied every tick: Windows resets clipping on many events
        else:
            self._release_clip()
            if fg and window_pid(fg) in self.exempt_pids:
                return   # e.g. hwlock's own window, opened from the tray to unlock: leave it in front
            # fg == 0 happens during UAC prompts / Ctrl+Alt+Del: leave those alone.
            if self.refocus and fg and time.monotonic() - self._last_refocus > REFOCUS_COOLDOWN:
                self._last_refocus = time.monotonic()
                if self._bring_to_front():
                    self.log("[lock] focus stolen, refocused target")

    # -------------------------------------------------------------- control
    def set_active(self, active):
        self.active = active
        if not active:
            self._release_clip()
        self.log(f"[lock] {'RESUMED' if active else 'PAUSED'} (Ctrl+Shift+F11 to toggle)")

    def stop(self):
        """Stop a lock running on another thread (e.g. from a GUI)."""
        self._stop_requested = True
        if self._thread_id:
            w.PostThreadMessageW(self._thread_id, w.WM_QUIT, 0, 0)

    def run(self):
        w.enable_dpi_awareness()
        if self._target_alive():
            self.log(f"[lock] target: {process_exe(self.pid) or '?'} (pid {self.pid}) "
                     f"\"{window_title(self.hwnd)}\"")
        elif not self._acquire_target():
            self.log("[lock] target not running yet, waiting for it...")

        self._hook = w.SetWindowsHookExW(w.WH_KEYBOARD_LL, self._hook_proc, w.GetModuleHandleW(None), 0)
        if not self._hook:
            raise ctypes.WinError(ctypes.get_last_error())
        timer = w.SetTimer(None, 0, TICK_MS, None)
        self._thread_id = w.GetCurrentThreadId()
        self.log("[lock] running. Ctrl+Shift+F11 = pause/resume, Ctrl+Shift+F12 = quit")
        try:
            msg = wt.MSG()
            while not self._stop_requested and w.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == w.WM_TIMER and not msg.hWnd:
                    self._tick()
                else:
                    w.TranslateMessage(ctypes.byref(msg))
                    w.DispatchMessageW(ctypes.byref(msg))
        except KeyboardInterrupt:
            self.log("[lock] interrupted")
        finally:
            w.KillTimer(None, timer)
            w.UnhookWindowsHookEx(self._hook)
            self._release_clip()
            self.log("[lock] released")
