"""hwlock command line.

    python -m hwlock devices [--all] [-v]
    python -m hwlock windows
    python -m hwlock lock Trackmania.exe [--clip-mouse] [--block win,alttab] [--no-refocus]
"""
import argparse
import sys

from devices import list_devices
from lock import BLOCKABLE, DEFAULT_BLOCK, FocusLock
from windows import list_windows


def cmd_devices(args):
    devices = list_devices(include_hid=args.all)
    if not devices:
        print("No input devices found.")
        return
    print(f"{'TYPE':<9} {'CONNECTION':<10} {'VID:PID':<10} {'NAME':<40} MANUFACTURER")
    for d in devices:
        vidpid = f"{d.vid}:{d.pid}" if d.vid else "-"
        print(f"{d.kind:<9} {d.connection:<10} {vidpid:<10} {d.name[:40]:<40} {d.manufacturer}")
        if args.verbose:
            print(f"{'':<31} {d.instance_id}")


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


def main(argv=None):
    p = argparse.ArgumentParser(prog="hwlock", description="Manage input devices and lock them to an application.")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("devices", help="list connected keyboards and mice")
    d.add_argument("--all", action="store_true", help="also list other HID devices (controllers, headsets, ...)")
    d.add_argument("-v", "--verbose", action="store_true", help="show device instance IDs")
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

    args = p.parse_args(argv)
    if args.cmd == "lock" and not (args.process or args.title):
        lk.error("give a process name or --title")
    args.func(args)


if __name__ == "__main__":
    main()
