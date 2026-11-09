# hwlock

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

You can also launch via the package entry point:
```powershell
python __main__.py gui
```

---

## Features

### 1. Lock Mode (Step-by-Step)

Lock Mode keeps your focus and inputs tied to a chosen program (e.g., preventing accidental Alt+Tab, Start Menu popups, or mouse clicks escaping during full-screen games or kiosk tasks).

1. **Step 1 — Select Hardware:**
   - Detects all connected keyboards and mice (USB, Bluetooth, built-in).
   - Tick the devices you want to include, then click **Select →**.
2. **Step 2 — Choose Program:**
   - Pick the target application from currently open windows.
   - Configure protection options:
     - **Refocus Target:** Automatically pulls the application back into the foreground if notifications or background processes steal focus.
     - **Block Keys:** Swallows escape keys (`Win`, `Alt+Tab`, `Alt+Esc`, `Ctrl+Esc`, `Menu/Apps`) so you don't drop out of the app.
     - **Confine Mouse Cursor:** Clips mouse movement to the target window boundaries when a mouse is selected.
3. **Auto-Unlock Timer:**
   - Check **Auto-unlock after** and set the duration in **hours** and **minutes**.
   - Upon pressing **Lock**, the lock activates and displays a live remaining countdown (e.g. `(00:24:59)`) in the status badge.
   - When the timer runs out, hwlock automatically releases the lock and restores normal input.
4. **Control & Tray:**
   - When the lock starts, hwlock minimizes to the system tray to stay out of your way.
   - Click the tray icon at any time to bring the window back and click **Unlock**.

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

#### Supported Editors & Limitations:
- **Compatible with:** Windows 11 Notepad, classic Notepad, Notepad++, and WordPad (standard Win32 `Edit`, `RichEdit`, and `Scintilla` controls).
- **Not compatible with:** Browser-based or Electron apps (VS Code, Discord, Obsidian), which drop keystrokes delivered while inactive in the background.
- Standard typing, Backspace, Enter, Tab, Arrow keys, and common shortcuts (`Ctrl+A`, `Ctrl+C`, `Ctrl+V`, `Ctrl+X`, `Ctrl+Z`, `Ctrl+Y`) work seamlessly.

---

## Global Hotkeys

These shortcuts operate globally across Windows while hwlock is active:

| Hotkey | Context | Action |
| :--- | :--- | :--- |
| <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>F10</kbd> | Notes Mode | Toggle typing redirection **on / off** (audio feedback) |
| <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>F11</kbd> | Lock Mode | **Pause / resume** keyboard and mouse confinement |
| <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>F12</kbd> | Any Mode | **Emergency Unlock / Stop** (restores window immediately) |

> **Safety note:** <kbd>Ctrl</kbd> + <kbd>Alt</kbd> + <kbd>Del</kbd> is reserved by the Windows kernel and will always work to regain system control.

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

## Command Line Usage (CLI)

hwlock includes a full command-line interface:

```powershell
# List input hardware (shows connection types: USB, Bluetooth, built-in)
python __main__.py devices

# Detailed device view (including instance IDs and HID collections)
python __main__.py devices --all -v

# List open application windows available to lock
python __main__.py windows

# Lock keyboard input to a specific process
python __main__.py lock Trackmania.exe

# Lock with mouse confinement to window borders
python __main__.py lock Trackmania.exe --clip-mouse

# Lock matching by window title with custom key blocking
python __main__.py lock --title "Trackmania" --block win,alttab,apps

# Start background Notes Mode directly to an editor
python __main__.py notes notepad.exe --on
```

---

## Project Structure

The project is organized into modular files and packages:

```text
hwlock/
├── run.py                 # Primary GUI launcher script
├── __main__.py            # CLI entry point and alternative runner
├── requirements.txt       # Python package dependencies
│
├── gui/                   # GUI package (CustomTkinter)
│   ├── __init__.py        # Re-exports App
│   ├── app.py             # Main CTk application window & tray lifecycle
│   ├── header.py          # Top navigation header & step indicators
│   ├── theme.py           # Color palette, font definitions, and status badges
│   ├── widgets.py         # Shared interactive UI components (ClickRow)
│   │
│   ├── lock_page/         # Lock Mode UI
│   │   ├── __init__.py
│   │   ├── device_page.py # Step 1: Hardware device selection
│   │   └── program_page.py# Step 2: Program selection, options & timer
│   │
│   └── notes_page/        # Notes Mode UI
│       ├── __init__.py
│       └── notes_page.py  # Editor selection & active notes controller
│
├── lock.py                # FocusLock engine (keyboard hook, focus management, mouse clipping)
├── notes.py               # NotesMode engine (Win32 SendNotifyMessage keystroke router)
├── devices.py             # Raw Input device enumeration and duplicate merging
├── windows.py             # Win32 window listing and process matching
├── tray.py                # System tray icon generator and menu controller
└── win32.py               # Low-level ctypes Win32 API bindings
```

---

## Important System Notes

- **Administrator Privileges:** If the game or target application is running as Administrator (elevated), Windows security (UIPI) prevents standard-user processes from sending input or refocusing it. Run hwlock as Administrator to match permissions.
- **DPI Awareness:** hwlock automatically enables Windows per-monitor DPI awareness to ensure precise mouse cursor clipping across multi-monitor setups.
- **Physical Keyboard Isolation:** In pure Win32 user-space, Windows routes all connected keyboards to the active foreground window. Isolating hardware at the driver level (e.g. keyboard A to Game, keyboard B to Desktop) requires a kernel filter driver such as Interception; device discovery in `devices.py` provides the hardware enumeration base for this workflow.
