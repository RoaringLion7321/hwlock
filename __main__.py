"""hwlock command line.

    python -m hwlock devices [--all] [-v]
    python -m hwlock windows
    python -m hwlock lock Trackmania.exe [--clip-mouse] [--block win,alttab] [--no-refocus]
    python -m hwlock notes [notepad.exe] [--title file.txt] [--on]
"""
import argparse
import sys

from devices import list_devices
from lock import BLOCKABLE, DEFAULT_BLOCK, FocusLock
from windows import list_windows


def cmd_devices(args):
    devices = list_devices(include_hid=args.all, merge=not args.raw, external_only=not args.all)
    if not devices:
        print("No input devices found.")
        return
    print(f"{'TYPE':<9} {'CONNECTION':<10} {'VID:PID':<10} {'NAME':<40} MANUFACTURER")
    for d in devices:
        vidpid = f"{d.vid}:{d.pid}" if d.vid else "-"
        print(f"{d.kind:<9} {d.connection:<10} {vidpid:<10} {d.name[:40]:<40} {d.manufacturer}")
        if args.verbose:
            for iid in d.interfaces or [d.instance_id]:
                print(f"{'':<31} {iid}")


def cmd_windows(_args):
    wins = sorted(list_windows(), key=lambda x: x.exe.lower())
    print(f"{'PID':>7}  {'PROCESS':<28} TITLE")
    for win in wins:
        print(f"{win.pid:>7}  {win.exe[:28]:<28} {win.title[:70]}")


def cmd_lock(args):
    block = [b.strip().lower() for b in args.block.split(",") if b.strip()] if args.block else []
    unknown = set(block) - set(BLOCKABLE)
    if unknown:
        sys.exit(f"unknown --block value(s): {', '.join(sorted(unknown))}. Choose from: {', '.join(BLOCKABLE)}")
    FocusLock(
        process=args.process,
        title=args.title,
        block=block,
        refocus=not args.no_refocus,
        clip_mouse=args.clip_mouse,
    ).run()


def cmd_notes(args):
    from notes import NotesMode
    NotesMode(process=args.process, title=args.title, start_on=args.on, sound=not args.quiet).run()


def cmd_gui(_args):
    import ctypes
    import customtkinter as ctk
    from gui.app import App

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("hwlock.app")
    except (AttributeError, OSError):
        pass
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    App().mainloop()


def main(argv=None):
    p = argparse.ArgumentParser(prog="hwlock", description="Manage input devices and lock them to an application.")
    sub = p.add_subparsers(dest="cmd")

    g = sub.add_parser("gui", help="launch the hwlock graphical interface")
    g.set_defaults(func=cmd_gui)

    d = sub.add_parser("devices", help="list connected keyboards and mice")
    d.add_argument("--all", action="store_true", help="also list built-in/virtual devices and other HID devices (controllers, headsets, ...)")
    d.add_argument("-v", "--verbose", action="store_true", help="show device instance IDs")
    d.add_argument("--raw", action="store_true", help="don't merge interfaces of the same physical device")
    d.set_defaults(func=cmd_devices)

    wn = sub.add_parser("windows", help="list running applications you can lock to")
    wn.set_defaults(func=cmd_windows)

    lk = sub.add_parser("lock", help="lock keyboard/mouse input to an application",
                        epilog="Hotkeys: Ctrl+Shift+F11 pause/resume, Ctrl+Shift+F12 quit.")
    lk.add_argument("process", nargs="?", help="process name, e.g. Trackmania.exe")
    lk.add_argument("--title", help="match a window title substring instead of / as well as the process")
    lk.add_argument("--block", default=",".join(DEFAULT_BLOCK),
                    help=f"comma-separated keys to block while the app is focused "
                         f"(default: {','.join(DEFAULT_BLOCK)}; options: {','.join(BLOCKABLE)}; '' for none)")
    lk.add_argument("--clip-mouse", action="store_true", help="confine the mouse cursor to the app window")
    lk.add_argument("--no-refocus", action="store_true", help="don't pull the app back to the front when it loses focus")
    lk.set_defaults(func=cmd_lock)

    nt = sub.add_parser("notes", help="type into a text editor while other windows are in front",
                        epilog="Hotkeys: Ctrl+Shift+F10 notes mode on/off, Ctrl+Shift+F12 quit.")
    nt.add_argument("process", nargs="?", default="notepad.exe", help="editor process (default: notepad.exe)")
    nt.add_argument("--title", help="match a window title substring (e.g. the file name)")
    nt.add_argument("--on", action="store_true", help="start with notes mode already on")
    nt.add_argument("--quiet", action="store_true", help="no sound when notes mode turns on/off")
    nt.set_defaults(func=cmd_notes)

    args = p.parse_args(argv)
    if not args.cmd:
        cmd_gui(args)
        return
    if args.cmd == "lock" and not (args.process or args.title):
        lk.error("give a process name or --title")
    args.func(args)


if __name__ == "__main__":
    main()
