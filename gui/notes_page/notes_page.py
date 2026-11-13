"""NotesPage — the Notes tab.

Lets the user pick a text editor, start the notes-mode hook, and toggle
whether keystrokes are being redirected into that editor.
Notes mode turns on automatically when Start is pressed.
"""
import os
import queue
import threading
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from core.notes import NotesMode, find_text_box
from core.windows import list_windows
from gui.theme import GREEN, GREEN_HOVER, MUTED, RED, RED_HOVER, STATUS, font
from gui.widgets import ClickRow


class NotesPage(ctk.CTkFrame):
    """Notes mode: pick a text editor, then type into it while other windows are in front."""

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app         = app
        self.editors     = {}   # key -> AppWindow
        self.rows        = {}   # key -> ClickRow
        self.radios      = []
        self.choice      = tk.StringVar()
        self.notes       = None
        self.thread      = None
        self.editor_name = ""
        self.log_queue   = queue.Queue()
        self._shown_on   = False   # the on/off state the status pill currently shows

        # ---- title + description ----
        ctk.CTkLabel(self, text="Notes mode", font=font(17, "bold")).pack(anchor="w")
        self.intro = ctk.CTkLabel(
            self, text="", font=font(13), text_color=MUTED, wraplength=700, justify="left", anchor="w",
        )
        self.intro.pack(anchor="w", pady=(0, 10))

        # ---- scrollable editor list ----
        self.list = ctk.CTkScrollableFrame(self, fg_color="transparent", height=200)
        self.list.pack(fill="both", expand=True)

        # ---- action bar ----
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", pady=(12, 0))

        self.refresh_btn = ctk.CTkButton(
            bar, text="\u21bb  Refresh", width=100, fg_color="transparent",
            border_width=1, text_color=("gray10", "gray90"), command=self.refresh,
        )
        self.refresh_btn.pack(side="left")

        self.status = ctk.CTkLabel(bar, text="", font=font(12, "bold"), corner_radius=12, height=28, width=170)
        self.status.pack(side="left", padx=8)

        self.start_btn = ctk.CTkButton(
            bar, text="\u25b6  Start", width=130, height=38, font=font(15, "bold"),
            fg_color=GREEN, hover_color=GREEN_HOVER, command=self.toggle_running,
        )
        self.start_btn.pack(side="right")

        self.onoff_btn = ctk.CTkButton(
            bar, text="Resume", width=110, height=38, font=font(14, "bold"),
            command=self.toggle_notes, state="disabled",
        )
        self.onoff_btn.pack(side="right", padx=8)

        # ---- footer hints ----
        self.hotkey_hint = ctk.CTkLabel(self, text="", font=font(12), text_color=MUTED)
        self.hotkey_hint.pack(anchor="e", pady=(6, 0))
        ctk.CTkLabel(
            self,
            text=(
                "Works with Notepad, Notepad++ and WordPad. "
                "Not with VS Code, Discord or other browser-based apps. "
                "While it's on, shortcuts in other windows don't work."
            ),
            font=font(12), text_color=MUTED, wraplength=700, justify="left",
        ).pack(anchor="w", pady=(4, 0))

        # ---- log box ----
        self.log_box = ctk.CTkTextbox(
            self, height=80, font=ctk.CTkFont(family="Consolas", size=12),
            corner_radius=10, state="disabled",
        )
        self.log_box.pack(fill="x", pady=(6, 0))

        self.show_hotkeys()
        self._set_status("stopped")
        self.refresh()
        self.after(100, self._poll)

    def show_hotkeys(self):
        """Show the current shortcuts (called again after they're changed in Settings)."""
        hk = self.app.hotkeys
        self.intro.configure(text=(
            "Type into a text editor while you click around other windows. "
            "Pick the editor and press Start — notes mode turns on automatically. "
            f"Use the Pause / Resume button (or {hk['pause']}) to switch it off and on."
        ))
        self.hotkey_hint.configure(
            text=f"{hk['pause']} pause / resume (works from any window)   •   {hk['stop']} stop"
        )

    # ------------------------------------------------------------------
    # Editor list
    # ------------------------------------------------------------------

    def refresh(self):
        """Re-enumerate windows that contain a supported text box."""
        prev      = self.editors.get(self.choice.get())
        prev_hwnd = prev.hwnd if prev else None
        for child in self.list.winfo_children():
            child.destroy()
        self.editors.clear()
        self.rows.clear()
        self.radios.clear()
        self.choice.set("")

        wins = [x for x in list_windows() if x.pid != os.getpid() and find_text_box(x.hwnd)[0]]
        for i, p in enumerate(sorted(wins, key=lambda x: x.exe.lower())):
            key = str(i)
            self.editors[key] = p
            row = ClickRow(self.list, on_click=lambda k=key: self._choose(k))
            row.pack(fill="x", pady=4, padx=(0, 6))

            radio = ctk.CTkRadioButton(
                row, text="", width=24, variable=self.choice, value=key,
                command=lambda k=key: self._choose(k),
            )
            radio.pack(side="left", padx=(14, 4), pady=12)

            text = ctk.CTkFrame(row, fg_color="transparent")
            text.pack(side="left", fill="x", expand=True, pady=8)
            ctk.CTkLabel(text, text=p.exe,        font=font(14, "bold"), anchor="w").pack(fill="x")
            ctk.CTkLabel(text, text=p.title[:80], font=font(12), text_color=MUTED, anchor="w").pack(fill="x")

            row.wire()
            self.rows[key]  = row
            self.radios.append(radio)
            if p.hwnd == prev_hwnd or len(wins) == 1:
                self._choose(key)

        if not self.editors:
            ctk.CTkLabel(
                self.list,
                text="No supported text editor is open. Open Notepad, then press Refresh.",
                text_color=MUTED,
            ).pack(pady=20)

    def _choose(self, key):
        self.choice.set(key)
        for k, row in self.rows.items():
            row.set_active(k == key)

    # ------------------------------------------------------------------
    # Start / stop
    # ------------------------------------------------------------------

    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def toggle_running(self):
        if self.running():
            self.notes.stop()
            return
        # Only one mode at a time (see ProgramPage.toggle_lock).
        if self.app.program_page.locked():
            messagebox.showwarning("hwlock", "A lock is active. Unlock it on the Lock tab before starting notes mode.")
            return
        editor = self.editors.get(self.choice.get())
        if not editor:
            messagebox.showwarning("hwlock", "Choose a text editor from the list.")
            return
        self.editor_name = editor.exe
        # start_on=True: notes mode is active the moment the hook is installed.
        self.notes  = NotesMode(hwnd=editor.hwnd, start_on=True, hotkeys=self.app.hotkeys,
                                log=self.log_queue.put)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self._set_running_ui(True)
        # GUI stays open so the user can toggle notes on/off with the button.

    def toggle_notes(self):
        """Toggle the notes-on/off state while the hook is running."""
        if self.running():
            self.notes.toggle()

    def _run(self):
        try:
            self.notes.run()
        except Exception as e:
            self.log_queue.put(f"[error] {e}")

    # ------------------------------------------------------------------
    # UI state helpers
    # ------------------------------------------------------------------

    def _set_status(self, kind: str, detail: str = ""):
        bg, fg, text = STATUS[kind]
        self.status.configure(text=f"\u25cf  {text}{detail}", fg_color=bg, text_color=fg)

    def _set_running_ui(self, running: bool):
        self._shown_on = False   # both branches below show the "off" state
        if running:
            self.start_btn.configure(text="\u25a0  Stop", fg_color=RED, hover_color=RED_HOVER)
            self.onoff_btn.configure(state="normal", text="Resume")
            self._set_status("notes_off")
        else:
            self.start_btn.configure(text="\u25b6  Start", fg_color=GREEN, hover_color=GREEN_HOVER)
            self.onoff_btn.configure(state="disabled", text="Resume")
            self._set_status("stopped")
        state = "disabled" if running else "normal"
        for widget in (self.refresh_btn, *self.radios):
            widget.configure(state=state)
        for row in self.rows.values():
            row.enabled = not running

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
        while not self.log_queue.empty():
            self._log(self.log_queue.get_nowait())

        # On / off: read NotesMode's own flag (same approach as the Lock page).
        if self.running():
            on = self.notes.on
            if on != self._shown_on:
                self._shown_on = on
                if on:
                    self._set_status("notes_on", f" {self.editor_name}")
                    self.onoff_btn.configure(text="Pause")
                else:
                    self._set_status("notes_off")
                    self.onoff_btn.configure(text="Resume")

        if self.thread is not None and not self.thread.is_alive():
            self.thread = None
            self._set_running_ui(False)
            self.app.show_again()

        self.after(100, self._poll)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def shutdown(self):
        """Stop notes mode cleanly on app exit."""
        if self.running():
            self.notes.stop()
            self.thread.join(timeout=1)
