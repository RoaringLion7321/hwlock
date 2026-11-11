"""Notes mode: type into a text editor while another window is in front.

Press Ctrl+Shift+F10 to switch notes mode on. From then on every key you type goes
into the chosen editor (Notepad, Notepad++, ...) even though it's in the background,
so you can click around a browser or a document with the mouse and keep writing.
Press Ctrl+Shift+F10 again to give the keyboard back to the window in front.

How it works:
  - A low-level keyboard hook (like lock.py) sees every key before any app does.
  - While notes mode is on, it swallows each key so the window in front never gets it,
    and sends it straight to the editor's text box with SendNotifyMessage:
      WM_KEYDOWN / WM_KEYUP for every key (arrows, Delete, Backspace, Enter, ...), and
      WM_CHAR with the character the key makes (worked out with ToUnicodeEx, using our
      own record of which keys are held, because Windows' record never sees swallowed keys).
  - SendNotifyMessage (not PostMessage) matters: posted key messages go through the
    editor's TranslateMessage, which would type every character a second time.
  - Ctrl shortcuts can't be sent as keys (the editor checks its own Ctrl state, which
    isn't held), so Ctrl+A/C/X/V/Z/Y are sent as the matching edit commands instead.

Works with classic Win32 text boxes: Windows 11 Notepad, classic Notepad, Notepad++, WordPad.
Doesn't work with Electron/browser apps (VS Code, Discord, ...), which ignore keys sent
to them while they're in the background.

Hotkeys (from any window):
  Ctrl+Shift+F10  notes mode on / off
  Ctrl+Shift+F12  quit
"""
import ctypes
import winsound
from ctypes import wintypes as wt

from core import win32 as w
from core.windows import find_window, window_pid

# Text box window classes we know how to type into, best first.
EDIT_CLASSES = (
    "RichEditD2DPT",   # Windows 11 Notepad
    "Scintilla",       # Notepad++
    "RICHEDIT50W",     # WordPad and other RichEdit apps
    "RichEdit20W",
    "Edit",            # classic Notepad and plain Win32 text boxes
)

TICK_MS = 500
TOUNICODE_NO_STATE_CHANGE = 0x4   # don't disturb dead-key state (Windows 10 1607+)

# Ctrl+<key> -> (message, wParam, lParam) sent to the text box
_SELECT_ALL = (w.EM_SETSEL, 0, -1)
CTRL_SHORTCUTS = {
    ord("A"): _SELECT_ALL,
    ord("C"): (w.WM_COPY, 0, 0),
    ord("X"): (w.WM_CUT, 0, 0),
    ord("V"): (w.WM_PASTE, 0, 0),
    ord("Z"): (w.WM_UNDO, 0, 0),
}
CTRL_REDO = ord("Y")

MODIFIERS = {w.VK_SHIFT, w.VK_CONTROL, w.VK_MENU, w.VK_LSHIFT, w.VK_RSHIFT,
             w.VK_LCONTROL, w.VK_RCONTROL, w.VK_LMENU, w.VK_RMENU, w.VK_LWIN, w.VK_RWIN}
# left/right modifier -> the generic one ToUnicodeEx looks at
GENERIC = {w.VK_LSHIFT: w.VK_SHIFT, w.VK_RSHIFT: w.VK_SHIFT, w.VK_LCONTROL: w.VK_CONTROL,
           w.VK_RCONTROL: w.VK_CONTROL, w.VK_LMENU: w.VK_MENU, w.VK_RMENU: w.VK_MENU}


def _class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    w.GetClassNameW(hwnd, buf, len(buf))
    return buf.value


def find_text_box(top):
    """The visible text box inside window `top` (Windows 11 Notepad has one per tab;
    only the current tab's is visible). Returns (hwnd, class name) or (None, None)."""
    found = {}

    @w.WNDENUMPROC
    def callback(hwnd, _):
        cls = _class_name(hwnd)
        if cls in EDIT_CLASSES and cls not in found and w.IsWindowVisible(hwnd):
            found[cls] = hwnd
        return True

    w.EnumChildWindows(top, callback, 0)
    for cls in EDIT_CLASSES:
        if cls in found:
            return found[cls], cls
    return None, None


def has_text_box(top):
    return find_text_box(top)[0] is not None


class KeyState:
    """Our own record of which keys are held. Windows' key state never sees keys the
    hook swallows, so ToUnicodeEx and the hotkeys have to use this instead."""

    def __init__(self):
        self.state = (ctypes.c_ubyte * 256)()
        if w.GetKeyState(w.VK_CAPITAL) & 1:
            self.state[w.VK_CAPITAL] = 0x01

    def update(self, vk, down):
        if vk == w.VK_CAPITAL and down and not self.state[vk] & 0x80:
            self.state[vk] ^= 0x01   # toggle on press
        self.state[vk] = (self.state[vk] & 0x01) | (0x80 if down else 0)
        if vk in GENERIC:
            gen = GENERIC[vk]
            left, right = {w.VK_SHIFT: (w.VK_LSHIFT, w.VK_RSHIFT), w.VK_CONTROL: (w.VK_LCONTROL, w.VK_RCONTROL),
                           w.VK_MENU: (w.VK_LMENU, w.VK_RMENU)}[gen]
            self.state[gen] = 0x80 if (self.state[left] | self.state[right]) & 0x80 else 0

    def held(self, vk):
        return bool(self.state[vk] & 0x80)

    def chars(self, vk, scan, layout):
        """The text this key makes right now ('' for keys like arrows or F1)."""
        buf = ctypes.create_unicode_buffer(8)
        n = w.ToUnicodeEx(vk, scan, self.state, buf, len(buf), TOUNICODE_NO_STATE_CHANGE, layout)
        return buf.value[:n] if n > 0 else ""


class NotesMode:
    def __init__(self, process=None, title=None, hwnd=None, start_on=False, sound=True, log=print):
        if not (process or title or hwnd):
            raise ValueError("need a process name, window title or window handle")
        self.process, self.title = process, title
        self.window = hwnd          # the editor's main window
        self.on = False
        self.sound = sound
        self.log = log
        self._start_on = start_on
        self.keys = KeyState()
        self._swallowed = set()     # keys whose key-down we took, so we also take the key-up
        self._box, self._box_class = None, None
        self._hook = None
        self._hook_proc = w.HOOKPROC(self._keyboard_proc)   # keep a reference (GC would crash Windows' call)
        self._thread_id = None
        self._stop_requested = False

    # ------------------------------------------------------------ target
    def _editor_alive(self):
        return bool(self.window) and w.IsWindow(self.window)

    def _find_editor(self):
        if self._editor_alive():
            return True
        if self.process or self.title:
            win = find_window(self.process, self.title)
            if win:
                self.window = win.hwnd
                self.log(f"[notes] editor: {win.exe} \"{win.title}\"")
                return True
        self.window = None
        return False

    def _text_box(self):
        """Current text box, re-found when it's gone or hidden (e.g. after switching Notepad tabs)."""
        box = self._box
        if box and w.IsWindow(box) and w.IsWindowVisible(box):
            return box
        self._box, self._box_class = (find_text_box(self.window) if self._editor_alive() else (None, None))
        return self._box

    # ------------------------------------------------------------ on / off
    def set_on(self, on):
        if on and not self._find_editor():
            self.log("[notes] editor isn't open, notes mode stays OFF")
            on = False
        elif on and not self._text_box():
            self.log("[notes] couldn't find a text box in that window, notes mode stays OFF")
            on = False
        if on == self.on:
            return
        self.on = on
        if self.sound:
            winsound.MessageBeep(winsound.MB_ICONASTERISK if on else winsound.MB_OK)
        self.log(f"[notes] {'ON: typing goes to the editor' if on else 'OFF: keyboard back to normal'}"
                 f" (Ctrl+Shift+F10 to toggle)")

    def toggle(self):
        self.set_on(not self.on)

    # ------------------------------------------------------------ keyboard
    def _keyboard_proc(self, n_code, w_param, l_param):
        if n_code == w.HC_ACTION:
            kb = ctypes.cast(l_param, ctypes.POINTER(w.KBDLLHOOKSTRUCT)).contents
            try:
                swallow = self._handle_key(kb, w_param in (w.WM_KEYDOWN, w.WM_SYSKEYDOWN))
            except Exception as e:   # never break the keyboard because of a bug
                self.log(f"[error] notes: {e}")
                swallow = False
            if swallow:
                return 1
        return w.CallNextHookEx(None, n_code, w_param, l_param)

    def _handle_key(self, kb, down):
        """Return True to swallow the key."""
        if kb.flags & w.LLKHF_INJECTED:
            return False   # software-generated keys (ours or other tools') pass untouched
        vk = kb.vkCode
        self.keys.update(vk, down)
        ctrl, shift, alt = (self.keys.held(w.VK_CONTROL), self.keys.held(w.VK_SHIFT),
                            self.keys.held(w.VK_MENU))

        # Hotkeys, checked with our own key record (Windows' doesn't see swallowed Ctrl/Shift).
        if vk in (w.VK_F10, w.VK_F12) and ctrl and shift:
            if down and vk not in self._swallowed:
                if vk == w.VK_F10:
                    self.toggle()
                else:
                    self.log("[notes] quit hotkey pressed")
                    w.PostQuitMessage(0)
            self._mark(vk, down)
            return True

        if not down:
            if vk in self._swallowed:
                self._swallowed.discard(vk)
                self._deliver_up(kb)
                return True
            return False

        if not self.on:
            return False
        if not self._editor_alive():
            self.set_on(False)
            return False

        self._swallowed.add(vk)
        self._deliver_down(kb, ctrl, alt)
        return True

    def _mark(self, vk, down):
        if down:
            self._swallowed.add(vk)
        else:
            self._swallowed.discard(vk)

    @staticmethod
    def _lparam(kb, up):
        lp = 1 | (kb.scanCode & 0xFF) << 16
        if kb.flags & w.LLKHF_EXTENDED:
            lp |= 1 << 24
        if up:
            lp |= 0xC0000000
        return lp

    def _send(self, box, msg, wparam, lparam):
        w.SendNotifyMessageW(box, msg, wparam, lparam)

    def _deliver_down(self, kb, ctrl, alt):
        vk = kb.vkCode
        if vk in MODIFIERS or vk == w.VK_CAPITAL:
            return   # tracked in KeyState; the editor doesn't need them
        box = self._text_box()
        if not box:
            return
        altgr = ctrl and alt   # AltGr = Ctrl+Alt on many European layouts (@, €, {, ...)
        if ctrl and not altgr:
            self._ctrl_shortcut(box, vk)
            return
        if alt and not altgr:
            return   # Alt+key would be menu shortcuts in the editor; ignore
        lparam = self._lparam(kb, up=False)
        self._send(box, w.WM_KEYDOWN, vk, lparam)
        layout = w.GetKeyboardLayout(w.GetWindowThreadProcessId(self.window, None))
        for ch in self.keys.chars(vk, kb.scanCode, layout):
            if ch == "\x1b":
                continue   # Esc makes a control character text boxes just beep at
            self._send(box, w.WM_CHAR, ord(ch), lparam)

    def _deliver_up(self, kb):
        vk = kb.vkCode
        if vk in MODIFIERS or vk == w.VK_CAPITAL:
            return
        box = self._text_box()
        if box:
            self._send(box, w.WM_KEYUP, vk, self._lparam(kb, up=True))

    def _ctrl_shortcut(self, box, vk):
        if vk in CTRL_SHORTCUTS:
            msg, wp, lp = CTRL_SHORTCUTS[vk]
            self._send(box, msg, wp, lp)
        elif vk == CTRL_REDO:
            if self._box_class == "Scintilla":
                self._send(box, w.SCI_REDO, 0, 0)
            elif self._box_class.startswith("RichEdit") or self._box_class == "RichEditD2DPT":
                self._send(box, w.EM_REDO, 0, 0)

    # ------------------------------------------------------------ lifecycle
    def _tick(self):
        if self.on and not self._editor_alive():
            self.log("[notes] editor closed")
            self.set_on(False)

    def stop(self):
        """Stop from another thread (e.g. a GUI)."""
        self._stop_requested = True
        if self._thread_id:
            w.PostThreadMessageW(self._thread_id, w.WM_QUIT, 0, 0)

    def run(self):
        if not self._find_editor():
            self.log("[notes] editor isn't open yet; open it, then press Ctrl+Shift+F10")
        self._hook = w.SetWindowsHookExW(w.WH_KEYBOARD_LL, self._hook_proc, w.GetModuleHandleW(None), 0)
        if not self._hook:
            raise ctypes.WinError(ctypes.get_last_error())
        self._thread_id = w.GetCurrentThreadId()
        timer = w.SetTimer(None, 0, TICK_MS, None)
        self.log("[notes] ready. Ctrl+Shift+F10 = notes mode on/off, Ctrl+Shift+F12 = quit")
        if self._start_on:
            self.set_on(True)
        try:
            msg = wt.MSG()
            while not self._stop_requested and w.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == w.WM_TIMER and not msg.hWnd:
                    self._tick()
                else:
                    w.TranslateMessage(ctypes.byref(msg))
                    w.DispatchMessageW(ctypes.byref(msg))
        except KeyboardInterrupt:
            self.log("[notes] interrupted")
        finally:
            w.KillTimer(None, timer)
            w.UnhookWindowsHookEx(self._hook)
            self.on = False
            self.log("[notes] stopped")
