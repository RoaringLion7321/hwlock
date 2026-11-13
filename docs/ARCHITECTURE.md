# How hwlock works

A walkthrough of every file, what it does, and why it's built that way.
For setup and usage see [README.md](../README.md); for project status see [HANDOFF.md](HANDOFF.md).

## The big picture

```
                        run.py  (no arguments → GUI, arguments → CLI)
                       ┌───┴────────────────┐
                       ▼                    ▼
   gui/  (CustomTkinter window + tray)    cli/  (argparse commands)
     │                                      │
     └──────────────┬───────────────────────┘
                    ▼
   core/   ┌────────────┐   ┌─────────────┐   ┌──────────┐
           │ devices.py │   │ windows.py  │   │ tray.py  │ (GUI only)
           │ what's     │   │ what's      │   │ tray     │
           │ plugged in │   │ running     │   │ icon     │
           └────────────┘   └──────┬──────┘   └──────────┘
                     ┌─────────────┴─────────────┐
                     ▼                           ▼
                  lock.py                     notes.py
                  FocusLock: keeps input      NotesMode: typing goes to
                  going to one window         a background editor

                    (everything sits on) win32.py
                     ctypes bindings to Windows' DLLs
```

The code is split into three packages:

- **`core/`** is the engine and has no GUI code:
  - **win32.py** is the bottom layer: it lets Python call Windows functions directly.
  - **devices.py** answers "which keyboards and mice are connected?"
  - **windows.py** answers "which programs have windows open?"
  - **lock.py** does the actual locking.
  - **notes.py** is notes mode: it sends your typing to a text editor that isn't in front.
  - **tray.py** draws the system tray icon (used by the GUI).
  - **settings.py** holds the configurable hotkeys and saves them to a JSON file.
- **`gui/`** is the window (CustomTkinter), split into one module per page.
- **`cli/`** is the command line.

`run.py` in the repo root is the entry point: with no arguments (or `gui`) it opens the
window, with any other arguments it hands them to the CLI. `python -m gui` and
`python -m cli <command>` work too. Imports are package-based (`from core.lock import FocusLock`),
so run everything from the repo root.

The CLI uses only the standard library. The GUI adds CustomTkinter, plus pystray and Pillow
for the tray icon (optional: without them the GUI runs without a tray icon). Everything talks
to Windows through Python's built-in `ctypes`.

---

## win32.py: talking to Windows

Python has no built-in way to install a keyboard hook or read device properties. Windows
offers these as C functions inside system DLLs (`user32.dll`, `kernel32.dll`, `cfgmgr32.dll`,
`dwmapi.dll`). `ctypes` can load those DLLs and call their functions, as long as we
describe each function's argument and return types.

The file has four parts:

1. **Loading the DLLs**: `ctypes.WinDLL("user32", use_last_error=True)` etc.
   `use_last_error` lets us read Windows' error code after a failed call.
2. **Constants**: numbers Windows expects, copied from the Windows headers. For example
   `WH_KEYBOARD_LL = 13` (the "low-level keyboard hook" type) or `VK_F12 = 0x7B` (the F12 key).
3. **Structures**: Python versions of C structs, e.g. `KBDLLHOOKSTRUCT` (what Windows
   passes to our keyboard hook: key code, flags, time) and `DEVPROPKEY` (identifies a
   device property such as "friendly name").
4. **Function prototypes**: `_proto(dll, name, restype, *argtypes)` looks a function up
   and records its types, so wrong arguments fail loudly in Python instead of crashing.

Two small helpers live here too:
- `enable_dpi_awareness()` makes window coordinates real pixels. Without it, on a 150%-scaled
  screen, mouse confining would use the wrong rectangle.
- `key_down(vk)` asks whether a key is held right now (`GetAsyncKeyState`).

---

## devices.py: what's plugged in

`list_devices()` returns a list of `Device` objects (kind, name, manufacturer, connection,
VID/PID, IDs). It works in four steps.

### 1. Ask Raw Input for every input device
`GetRawInputDeviceList` returns one entry per keyboard/mouse/HID *interface* that Windows
knows about, each with a handle and a type (`RIM_TYPEKEYBOARD`, `RIM_TYPEMOUSE`, `RIM_TYPEHID`).
`_device_path()` turns the handle into a device path like

```
\\?\HID#VID_1038&PID_1610&MI_00&Col02#8&33014c6&0&0001#{884b96c3-...}
```

and `_instance_id()` converts that into the Device Manager form
`HID\VID_1038&PID_1610&MI_00&Col02\8&33014c6&0&0001`.

What the pieces mean:
- `VID_1038` = vendor ID (1038 = SteelSeries, 046D = Logitech)
- `PID_1610` = product ID (the model)
- `MI_00` = USB interface number (one device can have several)
- `Col02` = HID collection inside that interface (one interface can also have several)

### 2. Look the device up in the device tree (`_describe`)
Windows keeps a tree of every device: USB controller → USB device → USB interface → HID
device → keyboard/mouse. The Configuration Manager API (`cfgmgr32`) lets us walk it:

- `CM_Locate_DevNodeW` finds the node for our instance ID.
- `CM_Get_DevNode_PropertyW` reads properties from a node (via `_raw_prop`, `_prop`, `_prop_list`).
- `CM_Get_Parent` moves one level up.

`_describe()` walks up to 5 levels and collects:
- **Name**: the "bus reported device description", which is the name the device itself
  reports over USB/Bluetooth (e.g. "SteelSeries Apex Pro"). It's much better than Windows'
  generic "HID Keyboard Device", which is used only as a fallback. Names from ACPI/PCI
  parents are ignored because they just say things like "PCI Device".
- **Connection** (`_connection`): if any node in the chain is `USB...` it's USB; `BTH...`
  means Bluetooth; a `ROOT\` or `SWD\` start means virtual (software-created); otherwise built-in.
- **Container ID** (`_container`): a GUID Windows gives each *physical* device. Every
  interface of the same keyboard shares it. Virtual devices get a placeholder
  (`NULL_CONTAINER`), which is treated as "no container".
- **Boot protocol** (`_boot_protocol`): see below.

### 3. Filter
By default only external devices (USB or Bluetooth) are kept, and plain HID devices
(headsets, RGB controllers, ...) are skipped. `list_devices(include_hid=True, external_only=False)`
returns everything (that's `devices --all` in the CLI). The GUI's hardware step calls
`list_devices(external_only=False)` and drops only `virtual` devices, so built-in laptop
keyboards and touchpads are listed.

### 4. Merge duplicates (`merge_duplicates`)
One physical device usually shows up as several entries. A gaming mouse also has a
"keyboard" collection (so its side buttons can send macros), and a keyboard has "mouse"
collections (media keys, volume dial). Unmerged, the Apex Pro appeared as 2 keyboards
and 3 mice.

The merge:
1. Groups entries by container ID (falling back to name + VID:PID + connection).
2. Decides what the device *really* is using the **USB boot protocol**. Every USB HID
   interface declares a class in its compatible IDs, e.g.
   `USB\Class_03&SubClass_01&Prot_01`. `Class_03` = HID, `SubClass_01` = "boot interface",
   `Prot_01` = keyboard, `Prot_02` = mouse. A device only declares the boot protocol for its
   main job, so the Aerox 3 says mouse and the Apex Pro says keyboard.
3. Keeps one entry per real type: a mouse stays a mouse, and a combo receiver (the Logitech
   Bolt declares both) stays as both. If no boot protocol is found (e.g. Bluetooth), it keeps
   one entry per type it saw.
4. Records every merged instance ID in `Device.interfaces`.

Finally the list is sorted keyboards first, then mice, then by name.

---

## windows.py: what's running

- `list_windows()` uses `EnumWindows` to visit every top-level window and keeps the ones
  that look like real apps (roughly what Alt+Tab shows): visible, has a title, isn't owned by
  another window, isn't "cloaked" (hidden UWP/virtual-desktop windows, checked with
  `DwmGetWindowAttribute`) and isn't the desktop itself (`Progman`/`WorkerW`). For each one it
  records the window handle, process ID, exe name, title and on-screen area.
- `window_pid(hwnd)` gives the process that owns a window.
- `process_exe(pid)` opens the process with minimal rights and reads its exe path.
- `window_title(hwnd)` and `class_name(hwnd)` read a window's title and window class
  (`class_name` is also what notes.py uses to recognise text boxes).
- `find_window(process, title)` picks the best match by exe name and/or title text. If several
  windows match, it takes the biggest, which is usually the main window rather than a popup.

---

## lock.py: the lock itself (`FocusLock`)

### The core problem
Windows sends keyboard input to whichever window is in the *foreground*. There's no
supported way to say "this keyboard belongs to that app". So "lock the keyboard to
Trackmania" really means: keep Trackmania in front, and stop the keys that would take you
away from it.

### Choosing the target
`FocusLock` takes a window handle (`hwnd`), a process name, a title substring, or a mix:
- The GUI passes the **exact window** picked in the list (`hwnd`) plus its exe name. Locking
  by exe name alone would pick that program's largest window, which is wrong when it has
  several (two Chrome windows, or Store apps, which all run as `ApplicationFrameHost.exe`).
- The CLI passes a process name and/or title, and `find_window` picks the best match.
- If the target window closes, the lock waits and re-attaches to `find_window(process, title)`
  when the program comes back (e.g. a restarted game). With only an `hwnd` it just waits.

"The target is in front" (`_target_focused`) means the foreground window is the target or a
window the target owns (its dialogs and message boxes, found with
`GetAncestor(fg, GA_ROOTOWNER)`). Other windows of the same process don't count.

### What runs
`run()` sets up three things on one thread, then loops on Windows messages:

1. **A low-level keyboard hook** (`SetWindowsHookExW(WH_KEYBOARD_LL, ...)`). Windows calls
   `_keyboard_proc` for every key press and release on the whole system *before* any app
   sees it. Returning 1 swallows the key; calling `CallNextHookEx` lets it through. The
   ctypes callback object is stored on `self` because if Python garbage-collected it,
   Windows would call into freed memory and crash.
2. **A 50 ms timer** (`SetTimer`), which makes Windows post a `WM_TIMER` message that runs
   `_tick()` 20 times a second.
3. **The message loop** (`GetMessageW` / `DispatchMessageW`). Hooks and timers only work while
   the thread keeps pumping messages, so this loop *is* the lock running. It ends on `WM_QUIT`.

### Deciding about each key (`_handle_key`)
1. **Hotkeys first.** The `lock_pause` hotkey (default Ctrl+Shift+F11) toggles pause; the `stop`
   hotkey (default Ctrl+Shift+F12) posts `WM_QUIT` to end the loop. Both are swallowed so the
   game doesn't see them. They come from `hotkeys=` (or `load_hotkeys()`, see settings.py) and
   are checked with `Hotkey.matches(vk, w.key_down)`: the lock never swallows Ctrl/Shift/Alt, so
   Windows' own key state is reliable here.
2. **Releases**: a key-up is swallowed only if its key-down was. That's what the `_swallowed`
   set is for; otherwise apps could think a key is stuck down.
3. **Pass-through cases**: paused, the key was injected by software (`LLKHF_INJECTED`), the
   target isn't running, or the target isn't in front. In those cases the lock does nothing.
4. **Blocking**: while the target is in front, swallow Win, Alt+Tab, Alt+Esc, Ctrl+Esc and
   optionally the Menu key, depending on the `block` set.

### Every tick (`_tick`)
- If the target window is gone (game closed), forget it, release the mouse and keep looking
  for it, so the lock re-attaches when the game comes back.
- If the target is in front and `clip_mouse` is on, `ClipCursor` confines the cursor to the
  window's client area. It's re-applied every tick because Windows quietly resets cursor
  clipping on many events (focus changes, resolution changes, UAC prompts).
- If something else is in front and `refocus` is on, bring the target back, at most every
  0.25 s (`REFOCUS_COOLDOWN`) so it never fights in a tight loop. If no window is in front
  (`GetForegroundWindow` returns 0), it leaves things alone: that happens during UAC prompts
  and Ctrl+Alt+Del.
- If the window in front belongs to one of the `exempt_pids`, it's left in front too (the
  cursor clip is still released, and keys pass through because the target isn't in front).
  The GUI passes its own process ID, so when you open hwlock from the tray during a lock, the
  lock doesn't push it away before you can click **Unlock**. Clicking back into the target
  resumes everything.

### Bringing a window to the front (`_bring_to_front`)
Windows deliberately makes this hard so random programs can't steal focus. Only the process
that last received input may change the foreground window. The function tries, in order:
1. Restore the window if it's minimized.
2. Briefly attach our thread's input to the current foreground thread (`AttachThreadInput`),
   which lets `SetForegroundWindow` succeed.
3. If that still fails, fake an Alt key tap (`keybd_event`). That counts as "we received input",
   so the next `SetForegroundWindow` is allowed.

### Running it from a GUI
`stop()` can be called from another thread: it sets a flag and posts `WM_QUIT` to the lock's
thread with `PostThreadMessageW`. The `finally` block in `run()` always unhooks, stops the
timer and releases the cursor, even after an error.

### Why it can't pick one keyboard
The hook tells us *which key* was pressed but not *which keyboard* it came from. Raw Input
knows the device but arrives after the hook has already decided. So without a filter driver,
locking applies to all keyboards (and `ClipCursor` to all mice), and the GUI's hardware step
offers exactly that choice: keyboard, mouse, or both. Binding a specific keyboard to a specific
window is a planned feature; see HANDOFF.md for the Interception idea and the two-keyboard
notes mode idea.

---

## notes.py: notes mode (`NotesMode`)

### The idea
You want to keep typing into Notepad while clicking around other windows. Windows would send
your keys to whatever window you last clicked, so notes mode catches them first and hands them
to Notepad directly.

### The pieces
- **Same hook as lock.py.** `run()` installs a low-level keyboard hook, starts a 500 ms timer
  and pumps messages, exactly like `FocusLock.run()`. The timer only checks that the editor
  is still open (and turns notes mode off if it closed).
- **Toggle.** The `notes_toggle` hotkey (default Ctrl+Shift+F10) calls `toggle()` → `set_on()`. Turning on fails (with a log
  message) if the editor or its text box can't be found. A Windows sound plays on each
  change, since you're usually looking at another window.
- **Finding the text box** (`find_text_box`). Keys have to go to the text box *inside* the
  editor, not its main window. `EnumChildWindows` lists the child windows and we take the first
  *visible* one whose class is known: `RichEditD2DPT` (Windows 11 Notepad), `Scintilla`
  (Notepad++), `RICHEDIT50W`/`RichEdit20W` (WordPad), `Edit` (classic Notepad). Windows 11
  Notepad has one text box per tab and hides the inactive ones, so `_text_box()` re-finds it
  whenever the cached one is gone or hidden.

### What happens to a key (`_handle_key`)
1. Software-generated keys (`LLKHF_INJECTED`) pass through untouched.
2. `KeyState.update()` records the key as held or released. This is hwlock's *own* record
   of the keyboard. Windows' record never sees keys the hook swallows, so if hwlock asked
   Windows "is Shift held?" while notes mode is on, the answer would always be no.
3. Hotkeys are checked against that record (`Hotkey.matches(vk, self.keys.held)`): `notes_toggle`
   (default Ctrl+Shift+F10) toggles, `stop` (default Ctrl+Shift+F12) quits. A held-down hotkey
   only fires once, because auto-repeat key-downs find the key already in `_swallowed`.
4. Notes mode off → let the key through. On → swallow it and deliver it (`_deliver_down`).
5. A key-up is swallowed (and delivered) only if its key-down was, using the `_swallowed` set,
   so keys pressed before toggling are released normally.

### Delivering a key (`_deliver_down` / `_deliver_up`)
A real key press reaches a text box as `WM_KEYDOWN`, then `WM_CHAR` (the character), then
`WM_KEYUP`. hwlock recreates that sequence:
- Modifiers (Shift, Ctrl, Alt, Win, Caps Lock) aren't sent; they only change `KeyState`.
- **Ctrl+key** (not AltGr) becomes an edit command instead (`_ctrl_shortcut`): Ctrl+A →
  `EM_SETSEL` (select all), Ctrl+C/X/V → `WM_COPY`/`WM_CUT`/`WM_PASTE`, Ctrl+Z → `WM_UNDO`,
  Ctrl+Y → redo (`EM_REDO` for any RichEdit class, matched case-insensitively so WordPad's
  `RICHEDIT50W` counts, or Scintilla's `SCI_REDO`). Sending Ctrl+C as plain keys
  wouldn't work, because the text box checks *its own* Ctrl state, which isn't held.
- **Alt+key** is ignored (it would trigger the editor's menus).
- **Everything else**: send `WM_KEYDOWN` (this is what moves the cursor for arrows, Delete,
  Home/End), then work out the character with `ToUnicodeEx`, using our `KeyState` and the
  *editor's* keyboard layout, and send it as `WM_CHAR`. That gives the right case for Shift and
  Caps Lock, and AltGr characters like `@` or `€` on European layouts. Backspace, Enter and Tab
  produce the characters `\b`, `\r` and `\t`, which text boxes handle like the real keys.
- Messages go out with `SendNotifyMessageW`, not `PostMessageW`. A *posted* `WM_KEYDOWN` goes
  through the editor's message loop, where `TranslateMessage` would make its own `WM_CHAR` and
  every letter would appear twice. A *sent* message skips that step, and `SendNotifyMessage`
  returns immediately, so a frozen editor can't stall the keyboard hook.

### Why some apps don't work
VS Code, Discord and other Electron/browser apps draw their own text boxes and only read the
keyboard while they're in front, so there's no Windows text box to send messages to.

---

## settings.py: configurable hotkeys

`ACTIONS` lists the three hotkey actions with their defaults: `notes_toggle` (Ctrl+Shift+F10),
`lock_pause` (Ctrl+Shift+F11) and `stop` (Ctrl+Shift+F12, ends whichever mode is running).

- **`Hotkey`** is one key (`vk`) plus an *exact* set of modifiers (`ctrl`, `shift`, `alt`).
  `str()` gives "Ctrl+Shift+F10" and `Hotkey.parse()` reads it back. `matches(vk, held)` takes
  a `held(vk)` function, because the lock asks Windows (`w.key_down`) while notes mode must ask
  its own `KeyState`. Modifiers must match exactly, so Ctrl+Shift+Q doesn't fire Ctrl+Q.
- **Rules** (`problem()` for one hotkey, `validate()` for the set): must include Ctrl, so a
  shortcut never eats normal typing or triggers a window's Alt menu; the key must be F1–F24,
  A–Z, 0–9, Space or a navigation key (`KEY_NAMES`); Ctrl+Alt+Delete is reserved; no two
  actions may share a shortcut. Win isn't offered as a modifier: the lock swallows the Win key,
  so Windows would never report it as held.
- **Storage**: `%APPDATA%\hwlock\settings.json` as `{"hotkeys": {"stop": "Ctrl+Alt+Q", ...}}`.
  `load_hotkeys()` never fails: a missing or broken file, or an invalid entry, falls back to the
  default (and a set with duplicates falls back to all defaults). `save_hotkeys()` validates,
  keeps any other keys in the file, and writes to a temp file then `os.replace`s it, so a crash
  can't leave a half-written file.

`FocusLock` and `NotesMode` take `hotkeys=` (the GUI passes `App.hotkeys`) and fall back to
`load_hotkeys()`, which is what the CLI uses.

The same file holds `"hide_welcome"`, the "Don't show this again" choice for the GUI's shortcuts
pop-up. `load_hide_welcome()` is True only for a literal `true` (anything else shows the pop-up),
and `save_hide_welcome()` rewrites just that key. Both savers go through `_write()` (temp file +
`os.replace`) and keep the rest of the file.

---

## tray.py: the system tray icon (`Tray`)

The GUI shows a tray icon for as long as hwlock runs. `make_icon()` draws a padlock on a
coloured rounded square with Pillow: blue = idle, green = locked or notes on, amber = lock
paused or notes running but off. Hovering shows a tooltip with the details.

pystray runs the icon on its own thread, and Tkinter may only be touched from the GUI thread.
So menu clicks are not handled in `tray.py`: each item just puts a plain string on a queue
(`"show"`, `"unlock"`, `"notes_toggle"`, `"notes_stop"`, `"quit"`), and the GUI reads that queue.
Menu items appear only when they apply (`visible=` callbacks read `locked` / `notes_running`).
`update()` is called from the GUI thread to change the colour, tooltip and menu state.

If pystray or Pillow isn't installed, importing `core.tray` fails, `core.Tray` is `None`, and
the GUI runs without a tray icon (closing the window then quits instead of hiding).

---

## gui/: the window

Built with CustomTkinter (a modern-looking layer over Python's standard Tkinter).

### Files
| File | What's in it |
|---|---|
| `gui/app.py` | `App` (the main window) and `main()`, the one function that launches the GUI |
| `gui/header.py` | `Header`: title, Lock / Notes tab switch, step chips, ⚙ settings button |
| `gui/settings_dialog.py` | `SettingsDialog`, the window for changing the keyboard shortcuts and the startup pop-up |
| `gui/welcome_dialog.py` | `WelcomeDialog`, the shortcuts pop-up shown at launch |
| `gui/theme.py` | shared colours (light/dark pairs), status-badge styles, key labels, `font()` |
| `gui/widgets.py` | `ClickRow`, the clickable list row used by every page |
| `gui/lock_page/device_page.py` | `DevicePage`, Lock step 1 |
| `gui/lock_page/program_page.py` | `ProgramPage`, Lock step 2 (program, options, timer, lock/unlock) |
| `gui/notes_page/notes_page.py` | `NotesPage`, the Notes tab |

### Structure
- **`main()`** sets the process's own taskbar ID (`SetCurrentProcessExplicitAppUserModelID`),
  so hwlock gets its own taskbar button instead of being grouped under Python, sets dark mode
  and runs `App`. `run.py`, `python -m gui` and `python -m cli gui` all call it.
- **`App`**: the main window. It holds a `Header` and three pages, and shows one at a time with
  `_show()` (`pack()` the page, `pack_forget()` the others). `switch_mode` handles the Lock/Notes
  tabs and remembers which Lock step you were on (`lock_page`). It also owns the tray:
  `_tray_poll()` runs every 150 ms, carries out queued tray commands and updates the icon when
  the state changes. `hide_to_tray()` hides the window when a lock starts (it minimizes instead
  if there's no tray icon), and `show_again()` brings it back. The window's close button hides
  hwlock to the tray; **Quit hwlock** in the tray menu quits for real (`_on_close`), stopping a
  running lock or notes mode first. It holds the hotkeys too: `App.hotkeys` is loaded at
  startup, `open_settings()` opens the Settings dialog (read-only while a mode runs), and
  `apply_settings()` stores a saved set and asks both pages to refresh their hint text
  (`show_hotkeys()`); the tray tooltip picks it up on its next poll. `App.hide_welcome` is
  loaded at startup too; unless it's set, `show_welcome()` opens the `WelcomeDialog` 300 ms
  after launch, and `_welcome_closed()` saves the checkbox if it changed.
- **`Header`**: the title, the **Lock / Notes** tab switch (a `CTkSegmentedButton`), the
  "1 Hardware / 2 Program" step chips and the ⚙ settings button. `set_step` highlights a chip;
  `show_steps` hides them on the Notes tab. The gear is packed before the chips so it stays
  rightmost when they're hidden and shown again.
- **`SettingsDialog`**: a modal window with one button per hotkey action. Clicking a button
  starts "recording": the dialog's `<KeyPress>` handler ignores lone modifiers, cancels on a
  bare Esc, and otherwise builds a `Hotkey` from the key (on Windows, Tk's `event.keycode` *is*
  the virtual-key code) and the Ctrl/Shift/Alt state read from Windows. No keyboard hook is
  running while the dialog can edit, so that state is accurate. Problems (`problem()`,
  duplicates via `validate()`) are shown in red; **Save** writes with `save_hotkeys()` and calls
  `App.apply_settings()`. Below the shortcuts, **Startup** has the "Don't show the shortcuts
  pop-up" checkbox (the same `hide_welcome` setting as the pop-up's own checkbox). While a lock
  or notes mode runs, the shortcut buttons and Reset are disabled, because the running hook would
  catch the keys being recorded (new hotkeys apply from the next start); the Startup checkbox and
  Save stay usable, and Save then only writes that checkbox.
- **`WelcomeDialog`**: a modal pop-up listing each hotkey (`App.hotkeys`), its label from
  `ACTIONS` and a longer explanation (`DETAILS`). OK, Enter, Esc and the window's X all close it
  and report the "Don't show this again" checkbox to `App._welcome_closed()`; **Change
  shortcuts…** closes it and opens Settings.
- **`ClickRow`**: a rounded list row that highlights on hover and reacts to clicks anywhere
  inside it. `wire()` walks every CustomTkinter widget inside the row (including nested
  frames) and binds click/hover. Checkboxes and radio buttons are skipped for clicks: they
  already toggle themselves, and running the row's click handler as well would toggle them
  straight back. It's used by the program and editor lists.
- **`DevicePage`** (step 1): matches how the lock really works (see "Why it can't pick one
  keyboard" above): the choice is per hardware *type*, not per device. Two toggle buttons,
  **Lock keyboard** (on by default) and **Lock mouse**, each in a column with a "Detected" list
  of the devices of that type. `refresh()` fills the lists from
  `list_devices(external_only=False)`, so built-in laptop keyboards and touchpads are shown;
  virtual (software) devices are left out of the list as noise, although the lock affects them
  too. Detection is informational only: a button works even if nothing of that type was
  detected, so laptops and unusual hardware are never blocked. `_paint()` colours the buttons
  and the "Locking: ..." summary; **Next** needs at least one button on and calls
  `App.show_programs(keyboard=..., mouse=...)`. A note on the page points to the planned
  per-keyboard binding.
- **`ProgramPage`** (step 2): `set_hardware(keyboard, mouse)` stores the choice
  (`lock_keyboard` / `lock_mouse`) and shows it as "All keyboards" / "All mice" badges. The page
  lists running programs (`list_windows()`, minus hwlock's own window) with radio buttons, and
  holds the options: refocus switch, which keys to block, and the **auto-unlock timer** (hours +
  minutes; the entries accept up to 3 digits and may be left empty, which counts as 0). The key
  options are disabled unless the keyboard is locked. After a refresh it re-selects the same
  program if it's still running.
- **`NotesPage`** (Notes tab): lists only windows that contain a supported text box
  (`find_text_box`), auto-selecting the only one if there's just one. **Start** runs `NotesMode`
  on a background thread for the chosen window, with notes mode already on; **Turn on/off**
  does the same as the notes hotkey. It uses the same thread + queue + `_poll()` pattern as the
  Lock page (below), and reads `NotesMode.on` on each poll to update its status pill and the
  Turn on/off button.

### How Lock works with threads
Tkinter must only be touched from its own thread, and `FocusLock.run()` blocks in its
message loop, so:
1. `toggle_lock()` builds a `FocusLock` for the chosen window (`hwnd`, plus its exe name for
   re-attaching), with hwlock's own process in `exempt_pids` so the lock never pushes the
   hwlock window away: `clip_mouse` is on if **Lock mouse** was chosen, and the blocked keys only
   apply if **Lock keyboard** was chosen. (Refocusing, when switched on, applies either way: it's
   what keeps the target in front.) It starts `run()` on a background **daemon thread** (one that
   won't keep Python alive on its own), then hides the window to the tray.
2. The lock never touches the GUI. Its `log` function is `queue.Queue.put`, which is thread-safe.
3. `_poll()` runs on the GUI thread every 100 ms. It moves log lines from the queue into the
   log box, updates the status pill (Locked / Paused, read from the lock's own `active` flag,
   never from log text, which contains arbitrary window titles), counts down
   the auto-unlock timer (calling `lock.stop()` when it reaches zero), and notices when the
   lock thread has ended (e.g. after the `stop` hotkey), then resets the buttons and shows the
   window again.
4. **Unlock** (button or tray menu) calls `lock.stop()`, which is safe from any thread.

While locked, Back, Refresh, the program list and the timer entries are disabled so nothing
can change underneath a running lock.

### Only one mode at a time
Lock and Notes each install their own keyboard hook, both use the same `stop` hotkey, and while
notes mode is on it swallows the modifier keys Lock's hotkeys need. So the GUI refuses to start
one while the other is running (`ProgramPage.toggle_lock` checks `notes_page.running()`,
`NotesPage.toggle_running` checks `program_page.locked()`) and explains why in a message box.

---

## cli/: command line

`cli/main.py` is `argparse` with five subcommands, each a thin wrapper. `run.py <command>` and
`python -m cli <command>` both reach it; with no command it opens the GUI.

| Command | Does |
|---|---|
| `devices [--all] [-v] [--raw]` | prints `list_devices()` as a table. `--all` includes built-in/virtual/HID devices, `-v` shows every instance ID behind a merged entry, `--raw` skips merging |
| `windows` | prints `list_windows()` |
| `lock <exe> [--title] [--block] [--clip-mouse] [--no-refocus]` | validates `--block` against `BLOCKABLE`, then runs `FocusLock` in the foreground until the `stop` hotkey or Ctrl+C |
| `notes [exe] [--title] [--on] [--quiet]` | runs `NotesMode` for an editor (default `notepad.exe`) until the `stop` hotkey or Ctrl+C |
| `gui` | opens the window (`gui.main()`) |

The GUI packages are imported only by `gui`, so the other commands work without them installed.
The CLI uses the hotkeys saved from the GUI's Settings (`load_hotkeys()`), and `lock --help` /
`notes --help` print the current ones and where the settings file is.
The one-mode-at-a-time rule is a GUI rule: two separate CLI processes could still run both.

---

## Other files

| File | Purpose |
|---|---|
| `run.py` | entry point: GUI with no arguments, CLI otherwise |
| `core/__init__.py` | re-exports the core classes/functions and `__version__`; `Tray` is `None` without pystray |
| `requirements.txt` | `customtkinter` for the GUI, `pystray` + `Pillow` for the tray icon (the CLI needs none) |
| `README.md` | setup and usage |
| `docs/ABSTRACT.md` | a short project overview: purpose, problem, approach |
| `docs/HANDOFF.md` | project status, limitations and ideas for the next session |
