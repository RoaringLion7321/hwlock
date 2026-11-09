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
- `notes.py`: `NotesMode`, notes mode (Idea A below, implemented 2026-11-06): Ctrl+Shift+F10 sends
  all typing to a background text editor.
- `__main__.py`: CLI (`py __main__.py devices | windows | lock <exe> | notes [exe]`).
- `gui.py`: CustomTkinter GUI with Lock / Notes tabs. Lock: 1. tick hardware → Select,
  2. pick a running program → Lock/Unlock. Notes: pick an editor → Start.
- `tray.py`: system tray icon (pystray + Pillow). The GUI hides into the tray when a lock or notes
  mode starts; the tray menu can show the window, unlock, toggle/stop notes, quit.
- `ARCHITECTURE.md`: how every file works. `ABSTRACT.md`: project abstract.
- Imports are flat (`from devices import ...`), so run everything from inside this folder.
- Python: use `py` (3.13). The Microsoft Store `python` couldn't see some folders.

## Known limitation
Windows can't route individual keyboards separately. Selecting any keyboard locks *all*
keyboard input; selecting any mouse confines the cursor for all mice. True per-device
locking needs a filter driver such as Interception. That's a possible next step
(an Interception integration was tried on 2026-11-06 and removed at the user's request).

## Device listing
- Only external (USB/Bluetooth) devices by default; `devices --all` for everything.
- Interfaces of one physical device are merged by container ID; the USB boot protocol
  (Prot_01 keyboard / Prot_02 mouse) decides whether it's shown as a keyboard or a mouse.
- Logitech Bolt receiver (046D:C548) shows as both, correctly; paired devices behind it would
  need Logitech HID++ over its vendor interface (MI_02). Not done.

## Not yet tested
Refocusing against Trackmania itself (only tested with Notepad, refocus off).
If the game runs as admin, hwlock must run as admin too.

## Ideas for next steps
- Per-device locking via the Interception driver
- Auto-lock when the game starts (the tray icon part of this idea is done)
- Saved profiles per game
- **Notes mode**: Idea A is implemented (`notes.py`); Idea B (two keyboards) isn't started

### Notes mode: type into a background text editor (no driver)
Use case: keep typing into Notepad while clicking around other windows (browser, docs)
to look things up. The mouse stays free; only the keyboard is redirected.

**Idea A: one keyboard + toggle hotkey (IMPLEMENTED in `notes.py`, see ARCHITECTURE.md)**
- Tested by feeding key events into the handler against real Windows 11 Notepad, Edit and
  RichEdit text boxes (typing, caps, Enter, Backspace, arrows, Ctrl+A/C/V/Z all correct).
  Not yet tried with physical keys or with Notepad++ (Scintilla).
- Differences from the plan below: keys go out with `SendNotifyMessage` (posting caused
  double characters via the editor's TranslateMessage); a built-in notes window wasn't added.
- Known gaps: Shift+arrow selection, Ctrl+arrow word jumps.
- Once (2026-11-06, right after the tray icon was added) the user reported Ctrl+Shift+F10 didn't
  turn notes mode *off*. It couldn't be reproduced (an injected-key test of the real hook passed
  on/type/off/on, with and without the tray) and later worked again for the user. If it comes
  back, suspect Windows silently removing the low-level hook (LowLevelHooksTimeout): the fix
  would be to detect that and reinstall the hook.
- User confirmed it works with real keys (2026-11-06). Letting any program be picked (keys to
  its focused control via `GetGUIThreadInfo`) was tried and removed at the user's request.

Original plan:
- A hotkey (e.g. Ctrl+Shift+F10) switches notes mode on/off.
- While on, the existing low-level keyboard hook (`lock.py`) swallows every key and
  delivers it to the editor's text control with `PostMessage` (`WM_KEYDOWN`/`WM_KEYUP`/`WM_CHAR`),
  even though the editor isn't in front.
- Find the edit control with `FindWindowEx`: classic Notepad `Edit`, Windows 11 Notepad
  `RichEditD2DPT`, Notepad++ `Scintilla`.
- Works for: Notepad, Notepad++, most classic Win32 editors. Not for Electron/browser apps
  (VS Code, Discord), which ignore posted keys. Fallback: a built-in hwlock notes window
  (a Tk text box that hwlock fills directly), which always works.
- Catch: while on, *all* keys go to the editor, so shortcuts in other windows (Ctrl+F in
  the browser) don't work until it's toggled off.

**Idea B: two keyboards, one always types into notes (experimental)**
- Goal: keyboard B always types into Notepad and keyboard A stays normal, with no toggle.
- Problem: the LL hook can block keys but doesn't know the device; Raw Input knows the
  device but arrives *after* the hook has already decided.
- Trick to try: the hook swallows every key and queues it; when the matching `WM_INPUT`
  (Raw Input with `RIDEV_INPUTSINK`) arrives a few ms later, look at the device:
  keyboard B -> post the key to Notepad; any other keyboard -> re-inject it with `SendInput`
  (the hook lets injected keys through via `LLKHF_INJECTED`).
- Unknown, test first: whether Windows still generates `WM_INPUT` for a key the LL hook
  swallowed. If not, this idea doesn't work without a driver.
- Side effects if it works: a few ms of latency on every key; re-injected keys are marked
  as injected (some games/anti-cheat ignore those, but normal apps don't care).

## Setup on a new PC
```
py -m pip install -r requirements.txt
py gui.py
```
