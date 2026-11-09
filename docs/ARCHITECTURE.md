# How hwlock works

A walkthrough of every file, what it does, and why it's built that way.
For setup and usage see [README.md](README.md); for project status see [HANDOFF.md](HANDOFF.md).

## The big picture

```
            ┌────────────┐      ┌─────────────┐
 gui.py ───►│ devices.py │      │ windows.py  │◄─── __main__.py (CLI)
   │        │ what's     │      │ what's      │          │
   │        │ plugged in │      │ running     │          │
   │        └─────┬──────┘      └──────┬──────┘          │
   │              │                    │                 │
   ├──────────────┴──────► lock.py ◄───┼─────────────────┤
   │                       FocusLock: keeps input going to one app
   │                                   │                 │
   └─────────────────────► notes.py ◄──┴─────────────────┘
                           NotesMode: typing goes to a background editor

                    (everything sits on) win32.py
                     ctypes bindings to Windows' DLLs
```

- **win32.py** is the bottom layer: it lets Python call Windows functions directly.
- **devices.py** answers "which keyboards and mice are connected?"
- **windows.py** answers "which programs have windows open?"
- **lock.py** does the actual locking.
- **notes.py** is notes mode: it sends your typing to a text editor that isn't in front.
- **gui.py** and **\_\_main\_\_.py** are two front ends (window and command line) over the same pieces.

No third-party packages are used except CustomTkinter for the GUI. Everything talks to
Windows through Python's built-in `ctypes`.

Imports are flat (`from devices import list_devices`), so run everything from inside this folder.

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
returns everything (that's `devices --all` in the CLI).

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
- `find_window(process, title)` picks the best match by exe name and/or title text. If several
  windows match, it takes the biggest, which is usually the main window rather than a popup.

---

## lock.py: the lock itself (`FocusLock`)

### The core problem
Windows sends keyboard input to whichever window is in the *foreground*. There's no
supported way to say "this keyboard belongs to that app". So "lock the keyboard to
Trackmania" really means: keep Trackmania in front, and stop the keys that would take you
away from it.

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
1. **Hotkeys first.** Ctrl+Shift+F11 toggles pause; Ctrl+Shift+F12 posts `WM_QUIT` to end the
   loop. Both are swallowed so the game doesn't see them.
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
locking applies to all keyboards (and `ClipCursor` to all mice). See HANDOFF.md for the
Interception idea and the two-keyboard notes mode idea.

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
- **Toggle.** Ctrl+Shift+F10 calls `toggle()` → `set_on()`. Turning on fails (with a log
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
3. Hotkeys are checked against that record (Ctrl+Shift+F10 toggle, Ctrl+Shift+F12 quit).
4. Notes mode off → let the key through. On → swallow it and deliver it (`_deliver_down`).
5. A key-up is swallowed (and delivered) only if its key-down was, using the `_swallowed` set,
   so keys pressed before toggling are released normally.

### Delivering a key (`_deliver_down` / `_deliver_up`)
A real key press reaches a text box as `WM_KEYDOWN`, then `WM_CHAR` (the character), then
`WM_KEYUP`. hwlock recreates that sequence:
- Modifiers (Shift, Ctrl, Alt, Win, Caps Lock) aren't sent; they only change `KeyState`.
- **Ctrl+key** (not AltGr) becomes an edit command instead (`_ctrl_shortcut`): Ctrl+A →
  `EM_SETSEL` (select all), Ctrl+C/X/V → `WM_COPY`/`WM_CUT`/`WM_PASTE`, Ctrl+Z → `WM_UNDO`,
  Ctrl+Y → redo (RichEdit `EM_REDO` or Scintilla `SCI_REDO`). Sending Ctrl+C as plain keys
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

## gui.py: the window

Built with CustomTkinter (a modern-looking layer over Python's standard Tkinter).

### Structure
- **`App`**: the main window. It holds a `Header` and three pages, and shows one at a time with
  `_show()` (`pack()` the page, `pack_forget()` the others). `switch_mode` handles the Lock/Notes
  tabs and remembers which Lock step you were on (`lock_page`). Closing the window stops a
  running lock and notes mode first (`_on_close`).
  `hide_to_taskbar()` minimizes the window when a lock or notes mode starts, and `show_again()`
  restores it when the pages' `_poll()` sees that it has ended. At startup the process sets its
  own taskbar ID (`SetCurrentProcessExplicitAppUserModelID`), so hwlock gets its own taskbar
  button instead of being grouped under Python.
- **`Header`**: the title, the **Lock / Notes** tab switch (a `CTkSegmentedButton`) and the
  "1 Hardware / 2 Program" step chips. `set_step` highlights a chip; `show_steps` hides them
  on the Notes tab.
- **`ClickRow`**: a rounded list row that highlights on hover and reacts to clicks anywhere
  inside it. `wire()` walks every CustomTkinter widget inside the row (including nested
  frames) and binds click/hover. Checkboxes and radio buttons are skipped for clicks: they
  already toggle themselves, and running the row's click handler as well would toggle them
  straight back. That was the "can't select hardware" bug.
- **`DevicePage`** (step 1): `refresh()` rebuilds the list from `list_devices()`. Each row has
  a checkbox, a coloured type badge, the name and a subtitle (connection, plus manufacturer
  unless it's a placeholder like "(Standard keyboards)"). `_changed()` repaints the rows and
  the "N selected" count; **Select** passes the ticked devices to step 2.
- **`ProgramPage`** (step 2): shows the chosen hardware as badges, lists running programs
  (`list_windows()`, minus hwlock's own window) with radio buttons, and holds the options:
  refocus switch and which keys to block. The key options are disabled if no keyboard was
  selected. After a refresh it re-selects the same program if it's still running.
- **`NotesPage`** (Notes tab): lists only windows that contain a supported text box
  (`find_text_box`), auto-selecting the only one if there's just one. **Start** runs `NotesMode`
  on a background thread for the chosen window; **Turn on/off** does the same as Ctrl+Shift+F10.
  It uses the same thread + queue + `_poll()` pattern as the Lock page (below), and reads
  "[notes] ON/OFF" log lines to update its status pill.

### How Lock works with threads
Tkinter must only be touched from its own thread, and `FocusLock.run()` blocks in its
message loop, so:
1. `toggle_lock()` builds a `FocusLock`: `clip_mouse` is on if a mouse was selected, and the
   blocked keys only apply if a keyboard was selected. It starts `run()` on a background
   **daemon thread** (one that won't keep Python alive on its own).
2. The lock never touches the GUI. Its `log` function is `queue.Queue.put`, which is thread-safe.
3. `_poll()` runs on the GUI thread every 100 ms. It moves log lines from the queue into the
   log box, updates the status pill (Locked / Paused, spotted from the log text) and notices
   when the lock thread has ended (e.g. after Ctrl+Shift+F12), then resets the buttons.
4. **Unlock** calls `lock.stop()`, which is safe from any thread.

While locked, Back, Refresh and the program list are disabled so the selection can't change
underneath a running lock.

---

## \_\_main\_\_.py: command line

`argparse` with four subcommands, each a thin wrapper:

| Command | Does |
|---|---|
| `devices [--all] [-v] [--raw]` | prints `list_devices()` as a table. `--all` includes built-in/virtual/HID devices, `-v` shows every instance ID behind a merged entry, `--raw` skips merging |
| `windows` | prints `list_windows()` |
| `lock <exe> [--title] [--block] [--clip-mouse] [--no-refocus]` | validates `--block` against `BLOCKABLE`, then runs `FocusLock` in the foreground until Ctrl+Shift+F12 or Ctrl+C |
| `notes [exe] [--title] [--on] [--quiet]` | runs `NotesMode` for an editor (default `notepad.exe`) until Ctrl+Shift+F12 or Ctrl+C |

---

## Other files

| File | Purpose |
|---|---|
| `__init__.py` | package docstring and `__version__` |
| `requirements.txt` | `customtkinter` (GUI only; the CLI needs nothing) |
| `README.md` | setup and usage |
| `HANDOFF.md` | project status, limitations and ideas for the next session |
| `test.txt` | empty, not used by the code |
