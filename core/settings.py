"""User settings: the global hotkeys and the startup pop-up, saved as JSON.

The file lives at %APPDATA%\\hwlock\\settings.json and looks like:

    {"hotkeys": {"notes_toggle": "Ctrl+Shift+F10",
                 "lock_pause":   "Ctrl+Shift+F11",
                 "stop":         "Ctrl+Shift+F12"},
     "hide_welcome": false}

"hide_welcome" is the "Don't show this again" choice for the shortcuts pop-up the GUI
shows at launch.

Anything missing or invalid falls back to the default, so a broken file never stops
hwlock from starting. The GUI edits it from the Settings dialog; the CLI reads it too.
"""
import json
import os
from dataclasses import dataclass

from core import win32 as w

# action id -> (default shortcut, what it does)
ACTIONS = {
    "notes_toggle": ("Ctrl+Shift+F10", "Notes mode on / off"),
    "lock_pause":   ("Ctrl+Shift+F11", "Pause / resume the lock"),
    "stop":         ("Ctrl+Shift+F12", "Stop lock / notes mode"),
}

# Keys a shortcut can end with: F1-F24, A-Z, 0-9 and the navigation block.
KEY_NAMES = {0x70 + i: f"F{i + 1}" for i in range(24)}
KEY_NAMES.update({c: chr(c) for c in range(ord("A"), ord("Z") + 1)})
KEY_NAMES.update({c: chr(c) for c in range(ord("0"), ord("9") + 1)})
KEY_NAMES.update({
    0x20: "Space", 0x21: "PageUp", 0x22: "PageDown", 0x23: "End", 0x24: "Home",
    0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down",
    0x2D: "Insert", 0x2E: "Delete", 0x13: "Pause", 0x91: "ScrollLock",
})
_NAME_TO_VK = {name.lower(): vk for vk, name in KEY_NAMES.items()}

# Modifier keys (generic, left/right and Win): pressing one alone doesn't finish a shortcut.
MODIFIER_VKS = {w.VK_SHIFT, w.VK_CONTROL, w.VK_MENU, w.VK_LSHIFT, w.VK_RSHIFT, w.VK_LCONTROL,
                w.VK_RCONTROL, w.VK_LMENU, w.VK_RMENU, w.VK_LWIN, w.VK_RWIN, w.VK_CAPITAL}

VK_DELETE = 0x2E


@dataclass(frozen=True)
class Hotkey:
    """A shortcut: one key plus an exact set of modifiers (Ctrl, Shift, Alt)."""
    vk: int
    ctrl: bool = False
    shift: bool = False
    alt: bool = False

    def __str__(self):
        mods = [name for name, on in (("Ctrl", self.ctrl), ("Shift", self.shift), ("Alt", self.alt)) if on]
        return "+".join(mods + [KEY_NAMES.get(self.vk, f"0x{self.vk:02X}")])

    @classmethod
    def parse(cls, text):
        """'Ctrl+Shift+F10' -> Hotkey. Raises ValueError for anything it can't read."""
        if not isinstance(text, str):
            raise ValueError("shortcut must be text")
        parts = [p.strip() for p in text.split("+") if p.strip()]
        if not parts:
            raise ValueError("empty shortcut")
        *mods, key = parts
        mods = {m.lower() for m in mods}
        unknown = mods - {"ctrl", "shift", "alt"}
        if unknown:
            raise ValueError(f"unknown modifier: {', '.join(sorted(unknown))}")
        vk = _NAME_TO_VK.get(key.lower())
        if vk is None:
            raise ValueError(f"unsupported key: {key}")
        return cls(vk, "ctrl" in mods, "shift" in mods, "alt" in mods)

    def matches(self, vk, held):
        """True if `vk` with exactly these modifiers is pressed. `held(vk)` says whether a
        modifier (VK_CONTROL / VK_SHIFT / VK_MENU) is down; the lock asks Windows, notes mode
        asks its own key record."""
        return (vk == self.vk
                and bool(held(w.VK_CONTROL)) == self.ctrl
                and bool(held(w.VK_SHIFT)) == self.shift
                and bool(held(w.VK_MENU)) == self.alt)


def default_hotkeys():
    return {action: Hotkey.parse(default) for action, (default, _desc) in ACTIONS.items()}


def problem(hotkey):
    """Why this shortcut can't be used, or None if it's fine."""
    if hotkey.vk not in KEY_NAMES:
        return "Use F1–F24, a letter, a digit, Space or a navigation key."
    if not hotkey.ctrl:
        return "Shortcuts must include Ctrl, so they don't get in the way of normal typing."
    if hotkey.alt and hotkey.vk == VK_DELETE:
        return "Ctrl+Alt+Delete is reserved by Windows."
    return None


def validate(hotkeys):
    """Check a full {action: Hotkey} set. Returns an error message, or None if it's fine."""
    for action, hk in hotkeys.items():
        err = problem(hk)
        if err:
            return f"{ACTIONS[action][1]}: {err}"
    seen = {}
    for action, hk in hotkeys.items():
        if hk in seen:
            return f"{hk} is used for both \"{ACTIONS[seen[hk]][1]}\" and \"{ACTIONS[action][1]}\"."
        seen[hk] = action
    return None


def settings_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "hwlock", "settings.json")


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load_hotkeys(path=None):
    """The saved hotkeys, with defaults for anything missing or invalid."""
    result = default_hotkeys()
    saved = _read(path or settings_path()).get("hotkeys")
    if isinstance(saved, dict):
        for action in ACTIONS:
            try:
                hk = Hotkey.parse(saved[action])
            except (KeyError, ValueError):
                continue
            if problem(hk) is None:
                result[action] = hk
    # e.g. a hand-edited file that gives two actions the same shortcut
    return default_hotkeys() if validate(result) else result


def save_hotkeys(hotkeys, path=None):
    """Validate and save. Raises ValueError (invalid set) or OSError (can't write)."""
    err = validate(hotkeys)
    if err:
        raise ValueError(err)
    path = path or settings_path()
    data = _read(path)   # keep any other settings in the file
    data["hotkeys"] = {action: str(hotkeys[action]) for action in ACTIONS}
    _write(path, data)


def load_hide_welcome(path=None):
    """True if the user chose "Don't show this again" for the startup shortcuts pop-up."""
    return _read(path or settings_path()).get("hide_welcome") is True


def save_hide_welcome(hide, path=None):
    """Save the "Don't show this again" choice. Raises OSError if the file can't be written."""
    path = path or settings_path()
    data = _read(path)   # keep the hotkeys and anything else in the file
    data["hide_welcome"] = bool(hide)
    _write(path, data)


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)   # atomic: a crash mid-write can't leave a half-written file
