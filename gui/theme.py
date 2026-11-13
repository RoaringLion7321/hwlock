"""Visual constants shared across all GUI pages: colours, fonts, status badges."""
import customtkinter as ctk

# ---------------------------------------------------------------------------
# Color pairs  (light-mode value, dark-mode value)
# ---------------------------------------------------------------------------
ROW        = ("#f1f3f6", "#2a2d33")
ROW_HOVER  = ("#e3e7ee", "#33373e")
ROW_ACTIVE = ("#dbe8fb", "#203550")
MUTED      = ("#6b7280", "#9aa1ab")

GREEN,  GREEN_HOVER  = "#2e9d57", "#257f47"
RED,    RED_HOVER    = "#d64545", "#b33939"

# Badge colours and labels for each device type
BADGE = {
    "keyboard": ("#3b82f6", "Keyboard"),
    "mouse":    ("#a855f7", "Mouse"),
    "hid":      ("#64748b", "HID"),
}

# Status-badge definitions: { key: (bg_pair, fg_pair, label) }
STATUS = {
    "idle":      (("#e5e7eb", "#3a3d44"), MUTED,                   "Not locked"),
    "locked":    (("#d6f5e1", "#1d3b2a"), ("#1f7a43", "#5fd38d"), "Locked"),
    "paused":    (("#fdf0d5", "#43361a"), ("#9a6700", "#f2c45a"), "Paused"),
    "stopped":   (("#e5e7eb", "#3a3d44"), MUTED,                   "Not running"),
    "notes_off": (("#fdf0d5", "#43361a"), ("#9a6700", "#f2c45a"), "Paused"),
    "notes_on":  (("#d6f5e1", "#1d3b2a"), ("#1f7a43", "#5fd38d"), "Typing into"),
}

# Human-readable labels for blockable key names
KEY_LABELS = {
    "win":     "Win",
    "alttab":  "Alt+Tab",
    "altesc":  "Alt+Esc",
    "ctrlesc": "Ctrl+Esc",
    "apps":    "Menu key",
}


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    """Return a Segoe UI CTkFont at the requested size and weight."""
    return ctk.CTkFont(family="Segoe UI", size=size, weight=weight)
