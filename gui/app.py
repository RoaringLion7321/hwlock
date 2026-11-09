"""App — the top-level CTk window.

Owns the header, the body frame that hosts the three pages, the page-switching
logic, the system-tray plumbing, and clean shutdown.
"""
import ctypes

import customtkinter as ctk

from gui.header              import Header
from gui.lock_page           import DevicePage, ProgramPage
from gui.notes_page          import NotesPage


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("hwlock")
        self.geometry("780x680")
        self.minsize(680, 580)

        # ---- header ----
        self.header = Header(self, on_mode=self.switch_mode)
        self.header.pack(fill="x", padx=20, pady=(16, 10))
        ctk.CTkFrame(self, height=1, fg_color=("#e5e7eb", "#34373d")).pack(fill="x", padx=20)

        # ---- body / pages ----
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=20, pady=(14, 18))
        self.device_page  = DevicePage(self.body, self)
        self.program_page = ProgramPage(self.body, self)
        self.notes_page   = NotesPage(self.body, self)
        self.lock_page    = self.device_page   # which Lock step was last visible
        self.show_devices()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # ---- system tray (optional — needs pystray + Pillow) ----
        self.tray, self._last_tray_status = None, None
        try:
            from tray import Tray
            self.tray = Tray()
            self.tray.start()
            self.after(150, self._tray_poll)
        except Exception as e:
            self.program_page._log(f"[tray] no tray icon: {e}")

    # ------------------------------------------------------------------
    # Page switching
    # ------------------------------------------------------------------

    def _show(self, page):
        """Show one page, hide the others."""
        for p in (self.device_page, self.program_page, self.notes_page):
            if p is not page:
                p.pack_forget()
        page.pack(fill="both", expand=True)

    def switch_mode(self, mode: str):
        """Called by the Lock / Notes segmented button in the header."""
        if mode == "Notes":
            self.header.show_steps(False)
            self._show(self.notes_page)
            if not self.notes_page.running():
                self.notes_page.refresh()
        else:
            self.header.show_steps(True)
            self._show(self.lock_page)

    def show_devices(self):
        self.lock_page = self.device_page
        self._show(self.device_page)
        self.header.set_step(0)

    def show_programs(self, devices):
        self.lock_page = self.program_page
        self.program_page.set_hardware(devices)
        self._show(self.program_page)
        self.header.set_step(1)

    # ------------------------------------------------------------------
    # Window visibility
    # ------------------------------------------------------------------

    def hide_to_tray(self):
        """Get out of the way once a lock starts: hide the window completely.
        The tray icon (always present while hwlock runs) brings it back."""
        if self.tray:
            self.after(150, self.withdraw)   # short delay so the new status is drawn first
        else:
            self.after(150, self.iconify)    # no tray icon: minimize instead

    def show_again(self):
        """Bring the window back (tray click, or hotkey ended a lock)."""
        if self.state() in ("withdrawn", "iconic"):
            self.deiconify()
        self.lift()
        self.focus_force()

    # ------------------------------------------------------------------
    # System tray
    # ------------------------------------------------------------------

    def _tray_status(self):
        """Return (state, tooltip, locked, notes_running, notes_on)."""
        pp, np_ = self.program_page, self.notes_page
        locked, notes_running = pp.locked(), np_.running()
        notes_on = notes_running and np_.notes.on
        parts, state = [], "idle"
        if locked:
            if pp.paused:
                parts.append("lock paused")
                state = "waiting"
            else:
                parts.append(f"locked to {pp.lock.process}")
                state = "active"
        if notes_running:
            if notes_on:
                parts.append(f"typing into {np_.editor_name}")
                state = "active"
            else:
                parts.append("notes ready (Ctrl+Shift+F10)")
                state = state if state == "active" else "waiting"
        tooltip = "hwlock: " + ", ".join(parts) if parts else "hwlock"
        return state, tooltip, locked, notes_running, notes_on

    def _tray_poll(self):
        """Drain tray commands and update the icon — called every 150 ms."""
        while not self.tray.commands.empty():
            cmd = self.tray.commands.get_nowait()
            if cmd == "show":
                self.show_again()
            elif cmd == "unlock" and self.program_page.locked():
                self.program_page.lock.stop()
            elif cmd == "notes_toggle":
                self.notes_page.toggle_notes()
            elif cmd == "notes_stop" and self.notes_page.running():
                self.notes_page.notes.stop()
            elif cmd == "quit":
                self._on_close()
                return

        status = self._tray_status()
        if status != self._last_tray_status:
            self._last_tray_status = status
            state, tooltip, locked, notes_running, notes_on = status
            self.tray.update(
                state=state, tooltip=tooltip, locked=locked,
                notes_running=notes_running, notes_on=notes_on,
            )
        self.after(150, self._tray_poll)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def _on_close(self):
        self.program_page.shutdown()
        self.notes_page.shutdown()
        if self.tray:
            self.tray.stop()
        self.destroy()
