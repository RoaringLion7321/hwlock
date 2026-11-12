# hwlock: Binding Input Hardware to an Application on Windows

## Overview

hwlock is a lightweight Windows utility, written in Python, that lists the keyboards and mice
connected to a computer and controls which application receives their input. It has two modes.
**Lock mode** binds the keyboard and mouse to a single program, such as a game, so that input
cannot be taken away from it. **Notes mode** does the reverse: it sends typing to a text editor
running in the background, so the user can keep writing while reading and clicking in other
windows. hwlock has a two-tab graphical interface built with CustomTkinter, with a system tray
icon that shows the current state, and a matching command line. Only one mode runs at a time. It talks to Windows directly through `ctypes`, so it needs no drivers, services or
installation.

## Purpose

hwlock gives users explicit control over a decision Windows normally makes for them: where
keyboard input goes. It is meant for two everyday situations:

1. **Focused play or work in one application.** A player wants every keystroke to reach the
   game, without notifications, pop-ups, overlays or an accidental Windows key switching away
   from it.
2. **Taking notes while researching.** A user wants to type into a notes file while freely
   clicking, scrolling and reading in a browser or another document.

The project also aims to be transparent and easy to learn from. Every part is documented
(see ARCHITECTURE.md), and the device listing shows clearly which physical hardware is connected.

## Problem

Windows sends all keyboard input to a single *foreground window*, the one most recently
clicked or activated. This causes problems in both situations above:

- **Input is easily taken away.** Any window that comes to the front, such as a notification,
  an update prompt, a chat overlay or a stray press of the Windows key or Alt+Tab, silently
  takes the keyboard. In a game this means lost inputs at critical moments.
- **Reading and writing can't happen at the same time.** Clicking into a browser to look
  something up moves the keyboard to the browser, so the user has to click back into their
  notes after every lookup.
- **The hardware picture is confusing.** Windows reports each internal channel of a device
  separately. A gaming mouse also appears as a "keyboard" (for its macro buttons), and a
  keyboard appears as several "mice" (for its media keys). This makes it hard to see or choose
  the actual devices.
- **Windows has no per-device routing.** There is no supported way to say "this keyboard
  belongs to that program". Doing this exactly requires a kernel-level filter driver, which
  adds installation risk, needs administrator rights and can be flagged by anti-cheat software.

## Proposed Solution

hwlock solves these problems in user mode, using only standard Windows interfaces:

- **Accurate device discovery.** Devices are listed through the Raw Input API and the Windows
  device tree (Configuration Manager). Entries belonging to the same physical device are merged
  by their *container ID*. The USB HID *boot protocol* each device declares then identifies its
  real type, so a mouse is shown as a mouse and a keyboard as a keyboard. The lock screen lists
  external (USB, Bluetooth) and built-in devices, so laptops are fully supported.
- **Lock mode (`FocusLock`).** A system-wide low-level keyboard hook blocks the keys that switch
  away from the target program (Windows key, Alt+Tab, Alt+Esc, Ctrl+Esc), but only while that
  program is in front. A 50 ms timer brings the program back if something else takes focus, and
  can keep the mouse cursor inside its window. The user chooses to lock the keyboard, the mouse,
  or both; this is per hardware type, matching what Windows allows. The lock follows the exact window the user picked,
  not just any window of that program. Hotkeys pause the lock (Ctrl+Shift+F11 by default) or end
  it (Ctrl+Shift+F12), an optional timer ends it automatically, and the lock re-attaches
  automatically if the program is restarted.
- **Notes mode (`NotesMode`).** With Ctrl+Shift+F10, the same kind of hook takes every keystroke
  away from the window in front and sends it straight to the chosen editor's text box. Characters
  are worked out from hwlock's own record of held keys and the editor's keyboard layout, so
  Shift, Caps Lock and international (AltGr) characters come out correctly. Common shortcuts
  (select all, copy, cut, paste, undo, redo) are turned into the matching edit commands. The
  mouse stays completely free, so the user can browse and read while their typing keeps going
  into Notepad, Notepad++ or WordPad.
- **Safe by design.** Locks are released cleanly on exit or error, keys are never left "stuck",
  and every mode can be turned off from any window with a hotkey. All hotkeys can be changed in
  a Settings window, with checks that keep them from clashing with each other or with typing.

**Limitations and future work.** Because Windows does not reveal which keyboard a hooked key came
from, lock mode applies to all keyboards and mouse confinement to all mice. Notes mode works with
classic Windows text boxes, but not with browser-based apps such as VS Code. The main planned
feature is binding specific keyboards to specific windows (e.g. one keyboard for a game, another
for notes) through an optional filter driver. Other possible next steps are a two-keyboard notes mode that routes
keys by the device they came from, saved per-game profiles, and automatic locking when a chosen
game starts.
