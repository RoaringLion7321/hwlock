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
        from gui import main as gui_main
        gui_main()


if __name__ == "__main__":
    main()
