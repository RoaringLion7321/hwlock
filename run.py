"""hwlock launcher.

Launch the GUI:
    python run.py             (or  pythonw run.py  to hide the console window)

Or run CLI commands:
    python run.py devices
    python run.py windows
    python run.py lock Trackmania.exe
    python run.py notes
"""
import sys


def main():
    # If arguments are passed, forward to the CLI module
    if len(sys.argv) > 1 and sys.argv[1] not in ("gui",):
        from cli.main import main as cli_main
        cli_main()
    else:
        import ctypes
        import customtkinter as ctk
        from gui import App

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
