# HWLock

A lightweight Windows utility to manage connected input devices, lock keyboard and mouse input to a specific application, and type into background editors with Notes mode.

Built with **Python + ctypes** (no external driver needed). The command-line interface has zero third-party dependencies, while the graphical interface is styled with **CustomTkinter** and features system tray integration via **pystray**.

---

## Installation

Ensure you have **Python 3.9+** installed on Windows.

Clone or download this repository, then install the required GUI and tray packages:

```powershell
pip install -r requirements.txt
```

---

## Quick Start

### Graphical Interface (GUI)

Launch the application using Python:

```powershell
python run.py
```

> **Tip:** Use `pythonw run.py` (or `pyw run.py`) to launch without a persistent console window.

You can also launch via the CLI module:
```powershell
python -m cli gui
```

---

## Features

### 1. Lock Mode (Step-by-Step)

Lock Mode keeps your focus and inputs tied to a chosen program (e.g., preventing accidental Alt+Tab, Start Menu popups, or mouse clicks escaping during full-screen games or kiosk tasks).

1. **Step 1 — Select Hardware:**
   - Choose **Lock keyboard**, **Lock mouse**, or both, then click **Next →** (keyboard is on by default).
   - Windows doesn't tell programs which keyboard or mouse an input came from, so the choice is
     per *type*: **Lock keyboard** applies to every keyboard and **Lock mouse** to every mouse,
     including built-in laptop keyboards and touchpads. The connected devices (USB, Bluetooth,
     built-in) are listed under each button so you can see what's covered. Binding one specific
     keyboard to one specific window is a [planned feature](#planned-features).
2. **Step 2 — Choose Program:**
   - Pick the target from currently open windows. The lock follows that exact window (and its
     own dialogs), even if the program has other windows open; if the window closes, hwlock
     re-attaches when the program opens a new one.
   - Configure protection options:
     - **Refocus Target:** Automatically pulls the application back into the foreground if notifications or background processes steal focus.
     - **Block Keys:** Swallows escape keys (`Win`, `Alt+Tab`, `Alt+Esc`, `Ctrl+Esc`, `Menu/Apps`) so you don't drop out of the app.
     - **Block Keys** is available when **Lock keyboard** was chosen in Step 1.
     - **Confine Mouse Cursor:** Clips mouse movement to the target window boundaries when **Lock mouse** was chosen in Step 1.
3. **Auto-Unlock Timer:**
   - Check **Auto-unlock after** and set the duration in **hours** and **minutes**.
   - Upon pressing **Lock**, the lock activates and displays a live remaining countdown (e.g. `(00:24:59)`) in the status badge.
   - When the timer runs out, hwlock automatically releases the lock and restores normal input.
4. **Control & Tray:**
   - When the lock starts, hwlock minimizes to the system tray to stay out of your way.
   - Click the tray icon at any time to bring the window back and click **Unlock**, or right-click
     the tray icon and choose **Unlock**, or press <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>F12</kbd>.
     While hwlock's own window is in front, the lock leaves it there (no refocusing, mouse not confined);
     clicking back into the program resumes it.
   - If the mouse is confined to the program, it can't reach the tray icon: press
     <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>F11</kbd> to pause first, or use
     <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>F12</kbd>.

#### How the lock works

Windows sends keyboard input only to the foreground window, so hwlock:

1. **Refocuses** the target whenever something else steals focus (popups, notifications, overlays).
   The target's own dialogs and hwlock's own window are left alone.
2. **Blocks escape keys** (Win, Alt+Tab, Alt+Esc, Ctrl+Esc, and optionally the Menu key) with a
   low-level keyboard hook, but only while the target is focused.
3. Optionally **confines the mouse** to the window (`--clip-mouse`).

---

### 2. Notes Mode (Type in the Background)

Notes Mode lets you type directly into a text editor (like Notepad) while keeping your browser, PDF viewer, or reference document open in front.

1. Switch to the **Notes** tab in the top navigation bar.
2. Select an open text editor from the list.
3. Click **Start**:
   - Notes mode **turns on automatically** the moment you start.
   - The GUI stays open so you can conveniently click **Turn off / Turn on** whenever you want to pause or resume redirection.
   - Keystrokes are routed directly into the editor's text control using Win32 message delivery without stealing window focus.
4. Use **Ctrl+Shift+F10** from any active window to toggle notes mode on and off on the fly (an audible chime confirms the switch).

While it's on, every key goes to the text editor, even though another window is in front. The mouse
works normally everywhere. Supported: letters and symbols (including AltGr), Enter, Tab,
Backspace, Delete, arrow keys, Home/End, Page Up/Down, and Ctrl+A / C / X / V / Z / Y.

#### Supported Editors & Limitations:
- **Compatible with:** Windows 11 Notepad, classic Notepad, Notepad++, and WordPad (standard Win32 `Edit`, `RichEdit`, and `Scintilla` controls).
- **Not compatible with:** Browser-based or Electron apps (VS Code, Discord, Obsidian), which drop keystrokes delivered while inactive in the background.
- Standard typing, Backspace, Enter, Tab, Arrow keys, and common shortcuts (`Ctrl+A`, `Ctrl+C`, `Ctrl+V`, `Ctrl+X`, `Ctrl+Z`, `Ctrl+Y`) work seamlessly.

---

> **One mode at a time:** Lock Mode and Notes Mode can't run together. Unlock before starting
> Notes Mode, and stop Notes Mode before locking; hwlock tells you if the other one is running.

## Global Hotkeys

These shortcuts operate globally across Windows while hwlock is active. The ones below are the
defaults; you can change them in [Settings](#settings) (everything in this README refers to the defaults).

| Default hotkey | Context | Action |
| :--- | :--- | :--- |
| <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>F10</kbd> | Notes Mode | Toggle typing redirection **on / off** (audio feedback) |
| <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>F11</kbd> | Lock Mode | **Pause / resume** keyboard and mouse confinement |
| <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>F12</kbd> | Any Mode | **Emergency Unlock / Stop** (restores window immediately) |

> **Safety note:** <kbd>Ctrl</kbd> + <kbd>Alt</kbd> + <kbd>Del</kbd> is reserved by the Windows kernel and will always work to regain system control.

---

## Settings

Click the **⚙** button at the top right of the window to change the keyboard shortcuts:

1. Click the shortcut you want to change; it shows **Press keys…**.
2. Press the new combination (e.g. <kbd>Ctrl</kbd> + <kbd>Alt</kbd> + <kbd>Q</kbd>). <kbd>Esc</kbd> cancels.
3. Click **Save**. **Reset to defaults** restores the shortcuts above.

Rules: every shortcut must include <kbd>Ctrl</kbd> (optionally with <kbd>Shift</kbd> and/or <kbd>Alt</kbd>)
and end with F1–F24, a letter, a digit, Space or a navigation key (arrows, Home/End, Page Up/Down,
Insert/Delete, Pause, Scroll Lock). Two actions can't share a shortcut, and
<kbd>Ctrl</kbd> + <kbd>Alt</kbd> + <kbd>Delete</kbd> is reserved by Windows. Modifiers must match
exactly, so <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>Q</kbd> doesn't trigger a <kbd>Ctrl</kbd> + <kbd>Q</kbd> shortcut.

Shortcuts can't be changed while Lock or Notes Mode is running, and new ones apply the next time
a mode starts. They're saved in `%APPDATA%\hwlock\settings.json`, which the command line uses too.

---

## System Tray Icon

hwlock displays a status icon in the notification area:

- 🔵 **Blue (Idle):** hwlock is open and waiting.
- 🟢 **Green (Active):** A program is currently locked, or Notes Mode is actively redirecting typing.
- 🟡 **Amber (Waiting / Paused):** Lock is paused (<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>F11</kbd>), or Notes Mode hook is running but turned off.

**Right-click the tray icon** to:
- Show/restore the hwlock window
- Unlock the current target program
- Toggle Notes Mode on/off
- Stop Notes Mode or exit hwlock completely

---

<!-- ## Command Line Usage (CLI)

hwlock includes a full command-line interface:

```powershell
# List input hardware (shows connection types: USB, Bluetooth, built-in)
python run.py devices

# Detailed device view (including instance IDs and HID collections)
python run.py devices --all -v

# List open application windows available to lock
python run.py windows

# Lock keyboard input to a specific process
python run.py lock Trackmania.exe

# Lock with mouse confinement to window borders
python run.py lock Trackmania.exe --clip-mouse

# Lock matching by window title with custom key blocking
python run.py lock --title "Trackmania" --block win,alttab,apps

# Start background Notes Mode directly to an editor
python run.py notes notepad.exe --on
```

*(You can also invoke directly via `python -m cli <command>`)*

--- -->

## Project Structure

The project has a clean root directory with all code modularized into packages:

```text
hwlock/
├── run.py                 # Primary entry point (runs GUI or CLI commands)
├── requirements.txt       # Python package dependencies
├── .gitignore             # Git ignore configuration
├── README.md              # Documentation
│
├── core/                  # Core Win32 & input engine
│   ├── __init__.py        # Re-exports core classes and functions
│   ├── devices.py         # Raw Input device enumeration and merging
│   ├── lock.py            # FocusLock engine (keyboard hook, focus, mouse clip)
│   ├── notes.py           # NotesMode engine (background keystroke routing)
│   ├── settings.py        # Hotkey settings: parsing, validation, load/save (JSON)
│   ├── windows.py         # Win32 window listing and process matching
│   ├── tray.py            # System tray icon generator and menu controller
│   └── win32.py           # Low-level ctypes Win32 API bindings
│
├── gui/                   # Graphical user interface (CustomTkinter)
│   ├── __init__.py        # Re-exports App and main
│   ├── __main__.py        # Allows `python -m gui`
│   ├── app.py             # main() launcher, main CTk window & tray lifecycle
│   ├── header.py          # Top navigation header, step indicators & settings button
│   ├── settings_dialog.py # Settings window (record new keyboard shortcuts)
│   ├── theme.py           # Color palette, font definitions, and status badges
│   ├── widgets.py         # Shared interactive UI components (ClickRow)
│   │
│   ├── lock_page/         # Lock Mode UI
│   │   ├── __init__.py
│   │   ├── device_page.py # Step 1: Lock keyboard / Lock mouse choice
│   │   └── program_page.py# Step 2: Program selection, options & timer
│   │
│   └── notes_page/        # Notes Mode UI
│       ├── __init__.py
│       └── notes_page.py  # Editor selection & active notes controller
│
├── cli/                   # Command line interface
│   ├── __init__.py
│   ├── main.py            # CLI argument parser and command handlers
│   └── __main__.py        # Allows `python -m cli`
│
└── docs/                  # Architecture & design documentation
    ├── ABSTRACT.md        # Project overview: purpose, problem, approach
    ├── ARCHITECTURE.md    # How every file works
    └── HANDOFF.md         # Status, known limitations, next steps
```

---

## Important System Notes

- **This only works on Windows OS**
- **Administrator Privileges:** If the game or target application is running as Administrator (elevated), Windows security (UIPI) prevents standard-user processes from sending input or refocusing it. Run hwlock as Administrator to match permissions.
- **DPI Awareness:** hwlock automatically enables Windows per-monitor DPI awareness to ensure precise mouse cursor clipping across multi-monitor setups.
- **Physical Keyboard Isolation:** In pure Win32 user-space, Windows routes all connected keyboards to the active foreground window. That's why Lock Mode works per hardware type (all keyboards / all mice). Isolating hardware at the driver level (e.g. keyboard A to Game, keyboard B to Desktop) requires a kernel filter driver such as Interception; device discovery in `devices.py` provides the hardware enumeration base for this workflow. See [Planned Features](#planned-features).

---

## Planned Features

- **Bind specific keyboards to specific windows.** Choose individual devices in Step 1 and give
  each its own target, e.g. keyboard A always goes to the game while keyboard B types into
  Notepad or stays with the desktop. This needs per-device input routing, which Windows doesn't
  offer to normal programs: the likely route is an optional filter driver such as
  [Interception](https://github.com/oblitum/Interception). See `docs/HANDOFF.md` for the
  design notes, including a driver-free experiment for a two-keyboard Notes Mode.
