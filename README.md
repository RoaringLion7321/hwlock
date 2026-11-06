# hwlock

Manage connected input hardware on Windows and lock keyboard/mouse input to one application.
Pure Python + ctypes (Python 3.9+). The command line has no dependencies; the GUI uses CustomTkinter.

## GUI

```
py -m pip install -r requirements.txt
py gui.py       # or: pyw gui.py  (no console window)
```

1. **Select hardware:** tick the keyboards/mice to lock and press **Select**.
2. **Choose a program:** pick one from the running programs and press **Lock** (**Unlock** to release).

Selected keyboards → keys are locked to the program; selected mice → cursor is confined to its window.

## Usage

Run from inside this folder:

```
py __main__.py devices            # keyboards & mice, with connection type (usb / bluetooth / built-in / virtual)
py __main__.py devices --all -v   # include other HID devices + instance IDs
py __main__.py windows            # running apps you can lock to
py __main__.py lock Trackmania.exe
py __main__.py lock Trackmania.exe --clip-mouse
py __main__.py lock --title "Trackmania" --block win,alttab,apps
```

While locked:

| Hotkey           | Action          |
|------------------|-----------------|
| Ctrl+Shift+F11   | pause / resume  |
| Ctrl+Shift+F12   | quit            |

Ctrl+Alt+Del always works (Windows doesn't let any app block it).

## How the lock works

Windows sends keyboard input only to the foreground window, so hwlock:

1. **Refocuses** the target whenever something else steals focus (popups, notifications, overlays).
2. **Blocks escape keys** (Win, Alt+Tab, Alt+Esc, Ctrl+Esc, and optionally the Menu key) with a
   low-level keyboard hook, but only while the target is focused.
3. Optionally **confines the mouse** to the window (`--clip-mouse`).

If the game closes, hwlock waits and re-locks once it's back.

## Notes

- If the game runs as administrator, run hwlock as administrator too, otherwise Windows blocks it from refocusing the game.
- Locking a *specific* keyboard (keyboard A goes to the game, keyboard B stays free) needs a
  filter driver such as Interception. Listing devices (`hwlock devices`) is the groundwork for that.
