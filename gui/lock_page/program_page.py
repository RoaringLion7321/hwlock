"""ProgramPage — Step 2 of the Lock flow: pick a program and start the lock.

Also owns the optional auto-unlock timer: a checkbox + hours/minutes entry
that stops the lock automatically when the countdown reaches zero.
"""
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from core.lock import BLOCKABLE, DEFAULT_BLOCK, FocusLock
from core.windows import list_windows
from gui.theme import BADGE, GREEN, GREEN_HOVER, MUTED, RED, RED_HOVER, STATUS, KEY_LABELS, font
from gui.widgets import ClickRow

ALL_LABEL = {"keyboard": "All keyboards", "mouse": "All mice"}


class ProgramPage(ctk.CTkFrame):
    """Step 2: show running programs and lock the selected hardware to one."""

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app      = app
        self.lock_keyboard = True    # chosen on DevicePage
        self.lock_mouse    = False
        self.programs = {}           # key -> AppWindow
        self.rows     = {}           # key -> ClickRow
        self.radios   = []
        self.choice   = tk.StringVar()
        self.lock        = None
        self.lock_thread = None
        self.target_name = ""        # shown in the status badge / tray tooltip while locked
        self.paused      = False
        self.log_queue   = queue.Queue()
        self._timer_end: float | None = None   # monotonic deadline; None = no timer

        # ---- title + hardware summary ----
        ctk.CTkLabel(self, text="Choose a program", font=font(17, "bold")).pack(anchor="w")
        self.summary = ctk.CTkFrame(self, fg_color="transparent")
        self.summary.pack(fill="x", pady=(2, 10))

        # ---- scrollable program list ----
        self.list = ctk.CTkScrollableFrame(self, fg_color="transparent", height=200)
        self.list.pack(fill="both", expand=True)

        # ---- options panel ----
        self._build_options()

        # ---- bottom action bar ----
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", pady=(12, 0))
        self.back_btn = ctk.CTkButton(
            bar, text="←  Back", width=90, fg_color="transparent",
            border_width=1, text_color=("gray10", "gray90"), command=app.show_devices,
        )
        self.back_btn.pack(side="left")
        self.refresh_btn = ctk.CTkButton(
            bar, text="↻  Refresh", width=100, fg_color="transparent",
            border_width=1, text_color=("gray10", "gray90"), command=self.refresh,
        )
        self.refresh_btn.pack(side="left", padx=8)
        self.status = ctk.CTkLabel(bar, text="", font=font(12, "bold"), corner_radius=12, height=28, width=150)
        self.status.pack(side="left", padx=8)
        self.lock_btn = ctk.CTkButton(
            bar, text="\U0001F512  Lock", width=140, height=38, font=font(15, "bold"),
            fg_color=GREEN, hover_color=GREEN_HOVER, command=self.toggle_lock,
        )
        self.lock_btn.pack(side="right")

        self.hotkey_hint = ctk.CTkLabel(self, text="", font=font(12), text_color=MUTED)
        self.hotkey_hint.pack(anchor="e", pady=(6, 0))
        self.log_box = ctk.CTkTextbox(
            self, height=90, font=ctk.CTkFont(family="Consolas", size=12),
            corner_radius=10, state="disabled",
        )
        self.log_box.pack(fill="x", pady=(6, 0))

        self.show_hotkeys()
        self._set_status("idle")
        self.after(100, self._poll)

    def show_hotkeys(self):
        """Show the current shortcuts (called again after they're changed in Settings)."""
        hk = self.app.hotkeys
        self.hotkey_hint.configure(
            text=f"While locked:  {hk['lock_pause']} pause / resume   •   {hk['stop']} unlock"
        )

    # ------------------------------------------------------------------
    # UI construction helpers
    # ------------------------------------------------------------------

    def _build_options(self):
        """Build the collapsible options panel (refocus switch, key blocks, timer)."""
        opts = ctk.CTkFrame(self, corner_radius=10)
        opts.pack(fill="x", pady=(12, 0))

        # Refocus switch
        self.refocus_var = tk.BooleanVar(value=True)
        ctk.CTkSwitch(
            opts,
            text="Pull the program back to the front if something steals focus",
            variable=self.refocus_var, font=font(13),
        ).pack(anchor="w", padx=14, pady=(12, 6))

        # Blocked-key checkboxes
        keys = ctk.CTkFrame(opts, fg_color="transparent")
        keys.pack(anchor="w", padx=14, pady=(0, 12))
        ctk.CTkLabel(keys, text="Block keys:", font=font(13), text_color=MUTED).pack(side="left", padx=(0, 8))
        self.block_vars, self.key_boxes = {}, []
        for name in BLOCKABLE:
            var = tk.BooleanVar(value=name in DEFAULT_BLOCK)
            box = ctk.CTkCheckBox(
                keys, text=KEY_LABELS[name], variable=var,
                width=20, font=font(13), checkbox_width=20, checkbox_height=20,
            )
            box.pack(side="left", padx=(0, 12))
            self.block_vars[name] = var
            self.key_boxes.append(box)

        # Auto-unlock timer row
        timer_row = ctk.CTkFrame(opts, fg_color="transparent")
        timer_row.pack(anchor="w", padx=14, pady=(0, 12))
        self.timer_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            timer_row, text="Auto-unlock after", variable=self.timer_var,
            width=20, font=font(13), checkbox_width=20, checkbox_height=20,
            command=self._timer_toggled,
        ).pack(side="left", padx=(0, 8))

        self.hours_var = tk.StringVar(value="0")
        self.mins_var  = tk.StringVar(value="25")
        # Allow "" so the field can be cleared while editing; _timer_seconds() reads "" as 0.
        vcmd = (self.register(lambda s: s == "" or (s.isdigit() and len(s) <= 3)), "%P")

        self._h_spin = ctk.CTkEntry(timer_row, textvariable=self.hours_var, width=52, font=font(13), justify="center")
        self._h_spin.configure(validate="key", validatecommand=vcmd)
        self._h_spin.pack(side="left")
        ctk.CTkLabel(timer_row, text="h", font=font(13), text_color=MUTED).pack(side="left", padx=(2, 8))

        self._m_spin = ctk.CTkEntry(timer_row, textvariable=self.mins_var, width=52, font=font(13), justify="center")
        self._m_spin.configure(validate="key", validatecommand=vcmd)
        self._m_spin.pack(side="left")
        ctk.CTkLabel(timer_row, text="min", font=font(13), text_color=MUTED).pack(side="left", padx=(2, 0))

        self._timer_toggled()   # set initial enabled/disabled state

    # ------------------------------------------------------------------
    # Hardware hand-off (called by App after DevicePage)
    # ------------------------------------------------------------------

    def set_hardware(self, keyboard: bool, mouse: bool):
        """Receive the choice from DevicePage (lock the keyboard, the mouse, or both)
        and refresh the program list."""
        self.lock_keyboard, self.lock_mouse = keyboard, mouse
        for child in self.summary.winfo_children():
            child.destroy()
        ctk.CTkLabel(self.summary, text="Locking", font=font(13), text_color=MUTED).pack(side="left", padx=(0, 6))
        for kind in self._kinds():
            ctk.CTkLabel(
                self.summary, text=ALL_LABEL[kind],
                font=font(12, "bold"), fg_color=BADGE[kind][0], text_color="white", corner_radius=10, height=24,
            ).pack(side="left", padx=3)
        for box in self.key_boxes:
            box.configure(state="normal" if keyboard else "disabled")
        self.refresh()

    def _kinds(self):
        """The chosen hardware kinds, e.g. ["keyboard", "mouse"]."""
        return [k for k, on in (("keyboard", self.lock_keyboard), ("mouse", self.lock_mouse)) if on]

    # ------------------------------------------------------------------
    # Program list
    # ------------------------------------------------------------------

    def refresh(self):
        """Re-enumerate running windows and rebuild the program list."""
        prev     = self.programs.get(self.choice.get())
        prev_exe = prev.exe if prev else None
        for child in self.list.winfo_children():
            child.destroy()
        self.programs.clear()
        self.rows.clear()
        self.radios.clear()
        self.choice.set("")

        for i, p in enumerate(sorted(list_windows(), key=lambda x: x.exe.lower())):
            if p.pid == os.getpid():   # don't offer hwlock's own window
                continue
            key = str(i)
            self.programs[key] = p
            row = ClickRow(self.list, on_click=lambda k=key: self._choose(k))
            row.pack(fill="x", pady=4, padx=(0, 6))

            radio = ctk.CTkRadioButton(row, text="", width=24, variable=self.choice, value=key,
                                       command=lambda k=key: self._choose(k))
            radio.pack(side="left", padx=(14, 4), pady=12)

            text = ctk.CTkFrame(row, fg_color="transparent")
            text.pack(side="left", fill="x", expand=True, pady=8)
            ctk.CTkLabel(text, text=p.exe,          font=font(14, "bold"), anchor="w").pack(fill="x")
            ctk.CTkLabel(text, text=p.title[:80],   font=font(12), text_color=MUTED, anchor="w").pack(fill="x")

            row.wire()
            self.rows[key] = row
            self.radios.append(radio)
            if p.exe == prev_exe and not self.choice.get():
                self._choose(key)

        if not self.programs:
            ctk.CTkLabel(self.list, text="No programs with windows found.", text_color=MUTED).pack(pady=20)

    def _choose(self, key):
        self.choice.set(key)
        for k, row in self.rows.items():
            row.set_active(k == key)

    # ------------------------------------------------------------------
    # Lock / unlock
    # ------------------------------------------------------------------

    def locked(self) -> bool:
        return self.lock_thread is not None and self.lock_thread.is_alive()

    def toggle_lock(self):
        if self.locked():
            self.lock.stop()
            return

        # Only one mode at a time: both install a keyboard hook with the same "stop"
        # hotkey, and Notes mode swallows the keys Lock's hotkeys need.
        if self.app.notes_page.running():
            messagebox.showwarning("hwlock", "Notes mode is running. Stop it on the Notes tab before locking.")
            return

        program = self.programs.get(self.choice.get())
        if not program:
            messagebox.showwarning("hwlock", "Choose a program from the list.")
            return

        duration = self._timer_seconds()
        if self.timer_var.get() and duration == 0:
            messagebox.showwarning("hwlock", "Set a timer duration greater than zero, or uncheck the timer.")
            return

        block = [k for k, v in self.block_vars.items() if v.get()] if self.lock_keyboard else []

        # hwnd = the exact window picked in the list (not just the largest window of that exe);
        # process lets the lock re-attach if that window closes and the program reopens.
        self.lock = FocusLock(
            process=program.exe or None, hwnd=program.hwnd, block=block,
            refocus=self.refocus_var.get(), clip_mouse=self.lock_mouse,
            exempt_pids={os.getpid()},   # don't push hwlock's own window away (Show / Unlock)
            hotkeys=self.app.hotkeys,
            log=self.log_queue.put,
        )
        self.target_name = program.exe or program.title[:40]
        self.lock_thread = threading.Thread(target=self._run_lock, daemon=True)
        self.lock_thread.start()

        what = " + ".join(ALL_LABEL[k].lower() for k in self._kinds())
        if duration:
            self._timer_end = time.monotonic() + duration
            h, m, s = duration // 3600, (duration % 3600) // 60, duration % 60
            self._log(f"Locking {what} → {self.target_name}  (timer: {h:02d}:{m:02d}:{s:02d})")
        else:
            self._timer_end = None
            self._log(f"Locking {what} → {self.target_name}")

        self._set_locked_ui(True, self.target_name)
        self.app.hide_to_tray()

    def _run_lock(self):
        try:
            self.lock.run()
        except Exception as e:
            self.log_queue.put(f"[error] {e}")

    # ------------------------------------------------------------------
    # Timer helpers
    # ------------------------------------------------------------------

    def _timer_toggled(self):
        """Enable/disable the hour and minute spinboxes to match the checkbox."""
        state = "normal" if self.timer_var.get() else "disabled"
        self._h_spin.configure(state=state)
        self._m_spin.configure(state=state)

    def _timer_seconds(self) -> int:
        """Return the timer duration in seconds, or 0 if disabled / zero."""
        if not self.timer_var.get():
            return 0
        try:
            h = max(0, int(self.hours_var.get() or 0))
            m = max(0, int(self.mins_var.get()  or 0))
        except ValueError:
            return 0
        return h * 3600 + m * 60

    # ------------------------------------------------------------------
    # UI state helpers
    # ------------------------------------------------------------------

    def _set_status(self, kind: str, detail: str = ""):
        bg, fg, text = STATUS[kind]
        self.status.configure(text=f"●  {text}{detail}", fg_color=bg, text_color=fg)

    def _set_locked_ui(self, locked: bool, exe: str = ""):
        if locked:
            self.lock_btn.configure(text="\U0001F513  Unlock", fg_color=RED, hover_color=RED_HOVER)
            self._set_status("locked", f" to {exe}")
        else:
            self.lock_btn.configure(text="\U0001F512  Lock", fg_color=GREEN, hover_color=GREEN_HOVER)
            self._set_status("idle")

        state = "disabled" if locked else "normal"
        for widget in (self.back_btn, self.refresh_btn, *self.radios):
            widget.configure(state=state)
        for row in self.rows.values():
            row.enabled = not locked

        # Freeze timer controls while a lock is active; restore them (respecting the
        # checkbox state) when it ends.
        if locked:
            for w in (self._h_spin, self._m_spin):
                w.configure(state="disabled")
        else:
            self._timer_toggled()

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log(self, text: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    # ------------------------------------------------------------------
    # Poll loop (runs every 100 ms on the GUI thread)
    # ------------------------------------------------------------------

    def _poll(self):
        # Drain the log queue from the background lock thread.
        while not self.log_queue.empty():
            self._log(self.log_queue.get_nowait())

        # Paused / resumed (pause hotkey): read the lock's own flag rather than parsing
        # log text, which can contain arbitrary window titles.
        if self.locked():
            paused = not self.lock.active
            if paused != self.paused:
                self.paused = paused
                if paused:
                    self._set_status("paused")
                else:
                    self._set_status("locked", f" to {self.target_name}")

        # Countdown timer: tick and auto-stop when it expires.
        if self.locked() and self._timer_end is not None:
            remaining = self._timer_end - time.monotonic()
            if remaining <= 0:
                self._log("[timer] Time's up — unlocking.")
                self._timer_end = None
                self.lock.stop()
            elif not self.paused:
                h = int(remaining) // 3600
                m = (int(remaining) % 3600) // 60
                s = int(remaining) % 60
                self._set_status("locked", f" to {self.target_name} ({h:02d}:{m:02d}:{s:02d})")

        # Detect when the background thread has ended.
        if self.lock_thread is not None and not self.lock_thread.is_alive():
            self.lock_thread = None
            self.paused      = False
            self._timer_end  = None
            self._set_locked_ui(False)
            self.app.show_again()

        self.after(100, self._poll)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def shutdown(self):
        """Stop the lock cleanly on app exit."""
        if self.locked():
            self.lock.stop()
            self.lock_thread.join(timeout=1)
