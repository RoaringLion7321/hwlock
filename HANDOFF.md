# Handoff notes (for continuing work with Claude on another PC)

Context from the first Claude Code session that built this project (2026-11-06).

## Goal
A Windows tool to manage connected input hardware and "lock" keyboards/mice to one
application (e.g. lock the keyboard to Trackmania so it always receives input).

## Current state
- `devices.py`: lists keyboards/mice/HID via Raw Input + cfgmgr32 (name, connection: usb/bluetooth/built-in/virtual).
- `windows.py`: lists visible top-level app windows and their processes.
- `lock.py`: `FocusLock`, which runs a low-level keyboard hook + 50 ms timer loop:
  - refocuses the target if focus is stolen,
  - blocks Win / Alt+Tab / Alt+Esc / Ctrl+Esc (/ Menu key) while the target is focused,
  - optional `ClipCursor` to confine the mouse,
  - hotkeys: Ctrl+Shift+F11 pause/resume, Ctrl+Shift+F12 quit; `stop()` for use from another thread.
- `__main__.py`: CLI (`py __main__.py devices | windows | lock <exe>`).
- `gui.py`: CustomTkinter two-step GUI (1. tick hardware → Select, 2. pick a running program → Lock/Unlock).
- Imports are flat (`from devices import ...`), so run everything from inside this folder.
- Python: use `py` (3.13). The Microsoft Store `python` couldn't see some folders.

## Known limitation
Windows can't route individual keyboards separately. Selecting any keyboard locks *all*
keyboard input; selecting any mouse confines the cursor for all mice. True per-device
locking needs a filter driver such as Interception. That's a possible next step.

## Not yet tested
Refocusing against Trackmania itself (only tested with Notepad, refocus off).
If the game runs as admin, hwlock must run as admin too.

## Ideas for next steps
- Per-device locking via the Interception driver
- System tray icon / auto-lock when the game starts
- Saved profiles per game

## Setup on a new PC
```
py -m pip install -r requirements.txt
py gui.py
```
