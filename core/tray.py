"""System tray icon for the hwlock GUI.

The icon is there for as long as hwlock runs. Its colour shows the state at a glance
(blue = idle, green = locked / notes on, amber = paused / notes ready), and hovering
shows the details. Clicking it (or "Show hwlock" in its menu) brings the window back.

pystray runs the icon on its own thread. Tkinter must only be touched from the GUI
thread, so menu clicks are not handled here: they're put on a queue as plain strings
("show", "unlock", "notes_toggle", "notes_stop", "quit") that the GUI reads in its poll loop.
"""
import queue
import threading

import pystray
from PIL import Image, ImageDraw

COLORS = {
    "idle": "#3b82f6",     # blue
    "active": "#2e9d57",   # green: locked, or notes mode on
    "waiting": "#d99a00",  # amber: lock paused, or notes running but off
}


def make_icon(color):
    """A 64x64 rounded square in `color` with a white padlock."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, 62, 62), radius=14, fill=color)
    d.rounded_rectangle((20, 10, 44, 38), radius=12, outline="white", width=6)   # shackle
    d.rounded_rectangle((14, 28, 50, 54), radius=5, fill="white")                 # body
    d.ellipse((28, 35, 36, 43), fill=color)                                        # keyhole
    d.rectangle((30.5, 40, 33.5, 48), fill=color)
    return img


class Tray:
    def __init__(self):
        self.commands = queue.Queue()
        self.locked = False         # a lock is running
        self.notes_running = False  # notes mode is running (on or off)
        self.notes_on = False
        self._icons = {k: make_icon(c) for k, c in COLORS.items()}
        self.icon = pystray.Icon("hwlock", self._icons["idle"], "hwlock", menu=self._menu())
        self._thread = None

    def _menu(self):
        send = lambda cmd: (lambda _icon, _item: self.commands.put(cmd))
        return pystray.Menu(
            pystray.MenuItem("Show hwlock", send("show"), default=True),   # default = left click
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Unlock", send("unlock"), visible=lambda _i: self.locked),
            pystray.MenuItem(lambda _i: "Pause notes mode" if self.notes_on else "Resume notes mode",
                             send("notes_toggle"), visible=lambda _i: self.notes_running),
            pystray.MenuItem("Stop notes mode", send("notes_stop"), visible=lambda _i: self.notes_running),
            pystray.MenuItem("Quit hwlock", send("quit")),
        )

    def start(self):
        self._thread = threading.Thread(target=self.icon.run, name="hwlock-tray", daemon=True)
        self._thread.start()

    def update(self, *, locked=None, notes_running=None, notes_on=None, tooltip="hwlock", state="idle"):
        """Called from the GUI thread whenever something changes."""
        if locked is not None:
            self.locked = locked
        if notes_running is not None:
            self.notes_running = notes_running
        if notes_on is not None:
            self.notes_on = notes_on
        self.icon.icon = self._icons[state]
        self.icon.title = tooltip[:127]   # Windows limits tray tooltips to 128 characters
        self.icon.update_menu()

    def stop(self):
        try:
            self.icon.stop()
        except Exception:
            pass
