"""DevicePage — Step 1 of the Lock flow: choose what to lock (keyboard, mouse or both).

Windows can't tell the lock which physical keyboard or mouse an input came from, so the
lock works per *type* of hardware, not per device: "Keyboard" locks every keyboard, "Mouse"
confines every mouse. The page says so, and lists the detected devices under each button
so it's clear what will be affected. (Binding a specific keyboard to a specific window is a
planned feature; it needs a filter driver, see docs/HANDOFF.md.)
"""
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from core.devices import list_devices
from gui.theme import BADGE, MUTED, ROW, ROW_HOVER, font

SELECTED, SELECTED_HOVER = "#3b82f6", "#2563eb"

# kind -> (button title, what it does)
CHOICES = {
    "keyboard": (
        "⌨  Lock keyboard",
        "Typing goes to the program. Blocks the keys that switch away from it "
        "(Win, Alt+Tab, ...). Applies to every keyboard.",
    ),
    "mouse": (
        "\U0001F5B1  Lock mouse",
        "Keeps the cursor inside the program's window. Applies to every mouse.",
    ),
}


class DevicePage(ctk.CTkFrame):
    """Step 1: two toggle buttons (keyboard / mouse) and the devices each one covers."""

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.vars = {kind: tk.BooleanVar(value=(kind == "keyboard")) for kind in CHOICES}
        self.buttons = {}   # kind -> CTkButton
        self.lists = {}     # kind -> frame holding the detected-device labels

        ctk.CTkLabel(self, text="Select hardware", font=font(17, "bold")).pack(anchor="w")
        ctk.CTkLabel(
            self,
            text=(
                "Choose what to lock to the program. Windows doesn't say which keyboard or mouse "
                "an input came from, so locking applies to all connected keyboards or mice, "
                "including built-in ones."
            ),
            font=font(13), text_color=MUTED, wraplength=700, justify="left", anchor="w",
        ).pack(anchor="w", fill="x", pady=(0, 12))

        cols = ctk.CTkFrame(self, fg_color="transparent")
        cols.pack(fill="both", expand=True)
        cols.grid_columnconfigure((0, 1), weight=1, uniform="col")
        cols.grid_rowconfigure(0, weight=1)
        for i, (kind, (title, desc)) in enumerate(CHOICES.items()):
            col = ctk.CTkFrame(cols, corner_radius=12)
            col.grid(row=0, column=i, sticky="nsew", padx=(0, 6) if i == 0 else (6, 0))

            btn = ctk.CTkButton(
                col, text=title, height=56, corner_radius=10, font=font(16, "bold"),
                command=lambda k=kind: self._toggle(k),
            )
            btn.pack(fill="x", padx=12, pady=(12, 8))
            self.buttons[kind] = btn
            ctk.CTkLabel(
                col, text=desc, font=font(12), text_color=MUTED,
                wraplength=300, justify="left", anchor="w",
            ).pack(fill="x", padx=14)

            ctk.CTkLabel(col, text="Detected", font=font(12, "bold"), anchor="w").pack(
                fill="x", padx=14, pady=(12, 2)
            )
            lst = ctk.CTkScrollableFrame(col, fg_color="transparent", height=120)
            lst.pack(fill="both", expand=True, padx=6, pady=(0, 10))
            self.lists[kind] = lst

        ctk.CTkLabel(
            self,
            text="Planned: bind a specific keyboard to a specific window (needs a driver).",
            font=font(12), text_color=MUTED, anchor="w",
        ).pack(anchor="w", pady=(8, 0))

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", pady=(12, 0))
        ctk.CTkButton(
            bar, text="↻  Refresh", width=110, fg_color="transparent",
            border_width=1, text_color=("gray10", "gray90"), command=self.refresh,
        ).pack(side="left")
        self.summary = ctk.CTkLabel(bar, text="", font=font(13), text_color=MUTED)
        self.summary.pack(side="left", padx=14)
        ctk.CTkButton(
            bar, text="Next  →", width=130, height=36,
            font=font(14, "bold"), command=self._next,
        ).pack(side="right")

        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self):
        """Re-enumerate devices and rebuild the "Detected" lists."""
        # Built-in devices count (laptop keyboards / touchpads); virtual software devices
        # are left out of the list as noise, though the lock affects them too.
        devices = [d for d in list_devices(external_only=False) if d.connection != "virtual"]
        for kind, lst in self.lists.items():
            for child in lst.winfo_children():
                child.destroy()
            found = [d for d in devices if d.kind == kind]
            if not found:
                ctk.CTkLabel(
                    lst, text=f"No {kind} detected (locking still works for any that connect).",
                    font=font(12), text_color=MUTED, wraplength=280, justify="left", anchor="w",
                ).pack(fill="x", padx=8, pady=4)
            for d in found:
                row = ctk.CTkFrame(lst, fg_color=ROW, corner_radius=8)
                row.pack(fill="x", pady=3, padx=(0, 4))
                ctk.CTkLabel(row, text=d.name, font=font(13, "bold"), anchor="w").pack(
                    fill="x", padx=10, pady=(6, 0)
                )
                ctk.CTkLabel(row, text=d.connection, font=font(11), text_color=MUTED, anchor="w").pack(
                    fill="x", padx=10, pady=(0, 6)
                )
        self._paint()

    def _toggle(self, kind):
        self.vars[kind].set(not self.vars[kind].get())
        self._paint()

    def _paint(self):
        """Colour the buttons by state and update the summary text."""
        for kind, btn in self.buttons.items():
            on = self.vars[kind].get()
            btn.configure(
                fg_color=SELECTED if on else ROW,
                hover_color=SELECTED_HOVER if on else ROW_HOVER,
                text_color="white" if on else ("gray10", "gray90"),
                border_width=0 if on else 1,
                border_color=BADGE[kind][0],
            )
        chosen = self.chosen()
        self.summary.configure(
            text="Locking: " + " + ".join(BADGE[k][1].lower() for k in chosen) if chosen
            else "Nothing selected"
        )

    def chosen(self):
        """The selected kinds, in display order: e.g. ["keyboard"] or ["keyboard", "mouse"]."""
        return [kind for kind in CHOICES if self.vars[kind].get()]

    def _next(self):
        """Validate the choice and hand off to the App."""
        if not self.chosen():
            messagebox.showwarning("hwlock", "Choose the keyboard, the mouse, or both.")
            return
        self.app.show_programs(keyboard=self.vars["keyboard"].get(), mouse=self.vars["mouse"].get())
