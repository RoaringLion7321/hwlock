"""DevicePage — Step 1 of the Lock flow: pick keyboards / mice to lock."""
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from core.devices import list_devices
from gui.theme import BADGE, MUTED, font
from gui.widgets import ClickRow


class DevicePage(ctk.CTkFrame):
    """Step 1: list connected devices, tick some, press Select."""

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app  = app
        self.rows = []   # list of (Device, BooleanVar, ClickRow)

        ctk.CTkLabel(self, text="Select hardware", font=font(17, "bold")).pack(anchor="w")
        ctk.CTkLabel(
            self,
            text="Choose the keyboards and mice you want to lock, then press Select.",
            font=font(13), text_color=MUTED,
        ).pack(anchor="w", pady=(0, 10))

        self.list = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.list.pack(fill="both", expand=True)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", pady=(12, 0))
        ctk.CTkButton(
            bar, text="↻  Refresh", width=110, fg_color="transparent",
            border_width=1, text_color=("gray10", "gray90"), command=self.refresh,
        ).pack(side="left")
        self.count = ctk.CTkLabel(bar, text="", font=font(13), text_color=MUTED)
        self.count.pack(side="left", padx=14)
        ctk.CTkButton(
            bar, text="Select  →", width=130, height=36,
            font=font(14, "bold"), command=self._select,
        ).pack(side="right")

        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self):
        """Re-enumerate devices and rebuild the list."""
        for child in self.list.winfo_children():
            child.destroy()
        self.rows.clear()

        devices = list_devices()
        if not devices:
            ctk.CTkLabel(
                self.list, text="No external keyboards or mice found.",
                text_color=MUTED,
            ).pack(pady=20)

        for d in devices:
            var = tk.BooleanVar()
            row = ClickRow(self.list, on_click=lambda v=var: (v.set(not v.get()), self._changed()))
            row.pack(fill="x", pady=4, padx=(0, 6))

            ctk.CTkCheckBox(row, text="", width=24, variable=var, command=self._changed).pack(
                side="left", padx=(14, 4), pady=12
            )
            color, label = BADGE.get(d.kind, BADGE["hid"])
            ctk.CTkLabel(
                row, text=label, font=font(11, "bold"),
                fg_color=color, text_color="white",
                corner_radius=8, width=74, height=22,
            ).pack(side="left", padx=(0, 12))

            text = ctk.CTkFrame(row, fg_color="transparent")
            text.pack(side="left", fill="x", expand=True, pady=8)
            ctk.CTkLabel(text, text=d.name, font=font(14, "bold"), anchor="w").pack(fill="x")
            # Skip manufacturers that just repeat the name or are driver placeholders.
            show_maker = (
                d.manufacturer
                and d.manufacturer != d.name
                and not d.manufacturer.startswith("(")
            )
            sub = d.connection + (f"  ·  {d.manufacturer}" if show_maker else "")
            ctk.CTkLabel(text, text=sub, font=font(12), text_color=MUTED, anchor="w").pack(fill="x")

            row.wire()
            self.rows.append((d, var, row))

        self._changed()

    def _changed(self):
        """Update the selection count label and row highlights."""
        n = 0
        for _d, var, row in self.rows:
            row.set_active(var.get())
            n += var.get()
        self.count.configure(text=f"{n} selected" if n else "Nothing selected")

    def _select(self):
        """Validate selection and hand off to the App."""
        selected = [d for d, var, _row in self.rows if var.get()]
        if not selected:
            messagebox.showwarning("hwlock", "Select at least one device first.")
            return
        self.app.show_programs(selected)
