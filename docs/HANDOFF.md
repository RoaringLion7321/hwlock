# Handoff notes (for continuing work with Claude on another PC)

Context from the Claude Code sessions that built this project (first session 2026-11-06,
last updated 2026-11-10).

## Goal
A Windows tool to manage connected input hardware and "lock" keyboards/mice to one
application (e.g. lock the keyboard to Trackmania so it always receives input).

## Current state
The code is in three packages; see [ARCHITECTURE.md](ARCHITECTURE.md) for how every file works.

- `core/devices.py`: lists keyboards/mice/HID via Raw Input + cfgmgr32 (name, connection:
  usb/bluetooth/built-in/virtual).
- `core/windows.py`: lists visible top-level app windows and their processes.
- `core/lock.py`: `FocusLock`, which runs a low-level keyboard hook + 50 ms timer loop:
  - locks to an exact window (`hwnd`, used by the GUI) or finds one by process/title (CLI),
    and re-attaches by process/title if the window closes and comes back,
  - refocuses the target if focus is stolen (the target's own dialogs don't count as stolen,
    and windows of `exempt_pids` are left in front: the GUI exempts itself so its window can
    be used to unlock),
  - blocks Win / Alt+Tab / Alt+Esc / Ctrl+Esc (/ Menu key) while the target is focused,
  - optional `ClipCursor` to confine the mouse,
  - hotkeys: Ctrl+Shift+F11 pause/resume, Ctrl+Shift+F12 quit; `stop()` for use from another thread.
- `core/notes.py`: `NotesMode`, notes mode (Idea A below): Ctrl+Shift+F10 sends all typing to
  a background text editor.
- `core/tray.py`: system tray icon (pystray + Pillow), colour-coded by state, with a menu
  (show, unlock, notes on/off, stop notes, quit).
- `cli/main.py`: CLI (`python run.py devices | windows | lock <exe> | notes [exe] | gui`).
- `gui/`: CustomTkinter GUI with Lock / Notes tabs, one module per page. Lock: 1. tick
  hardware → Select, 2. pick a running program → Lock/Unlock, with an optional auto-unlock
  timer. Notes: pick an editor → Start (notes mode turns on immediately). The window hides to
  the tray while locked. Only one of Lock / Notes can run at a time.
- `run.py`: entry point. No arguments → GUI, otherwise → CLI.
- Imports are package-based (`from core.lock import FocusLock`), so run everything from the
  repo root.
- Python: use `py` (3.13+; README says 3.9+). The Microsoft Store `python` couldn't see some folders.

## Known limitations
- Windows can't route individual keyboards separately. Selecting any keyboard locks *all*
  keyboard input; selecting any mouse confines the cursor for all mice. True per-device
  locking needs a filter driver such as Interception. That's a possible next step
  (an Interception integration was tried on 2026-11-06 and removed at the user's request).
- The hardware step lists external (USB/Bluetooth) devices only, and needs at least one
  ticked, so a laptop with nothing plugged in can't get past step 1 in the GUI.
- With a mouse selected, the cursor is confined to the target, so the tray icon can't be
  reached with the mouse; pause (Ctrl+Shift+F11) or quit (Ctrl+Shift+F12) first.
- Notes mode keeps its own record of held keys. After Ctrl+Alt+Del or a UAC prompt, the
  key releases happen on the secure desktop and are never seen, so Ctrl/Alt can look stuck
  until they're tapped again.

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
- Auto-lock when the game starts (the system tray icon is done)
- Saved profiles per game
- **Notes mode**: Idea A is implemented (`core/notes.py`); Idea B (two keyboards) isn't started

### Notes mode: type into a background text editor (no driver)
Use case: keep typing into Notepad while clicking around other windows (browser, docs)
to look things up. The mouse stays free; only the keyboard is redirected.

**Idea A: one keyboard + toggle hotkey (IMPLEMENTED in `core/notes.py`, see ARCHITECTURE.md)**
- Tested by feeding key events into the handler against real Windows 11 Notepad, Edit and
  RichEdit text boxes (typing, caps, Enter, Backspace, arrows, Ctrl+A/C/V/Z all correct).
  Not yet tried with physical keys or with Notepad++ (Scintilla).
- Differences from the plan below: keys go out with `SendNotifyMessage` (posting caused
  double characters via the editor's TranslateMessage); a built-in notes window wasn't added.
- Known gaps: Shift+arrow selection, Ctrl+arrow word jumps.
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
py run.py
```
