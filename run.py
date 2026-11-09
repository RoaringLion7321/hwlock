"""hwlock GUI launcher.

Requires:  pip install -r requirements.txt
Run with:  python gui.py   (or  pythonw gui.py  to hide the console window)
Run with:  python run.py   (or  pythonw run.py  to hide the console window)
"""
import ctypes

import customtkinter as ctk

from gui import App


def main():
    # Own taskbar identity, so hwlock gets its own taskbar button instead of being grouped
    # under (and labeled as) Python.
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("hwlock.app")
    except (AttributeError, OSError):
        pass
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    App().mainloop()


if __name__ == "__main__":
    main()
