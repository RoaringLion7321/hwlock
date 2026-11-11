"""hwlock GUI module entry point (`python -m gui`)."""
from gui.app import App
import ctypes
import customtkinter as ctk


def main():
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("hwlock.app")
    except (AttributeError, OSError):
        pass
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    App().mainloop()


if __name__ == "__main__":
    main()
