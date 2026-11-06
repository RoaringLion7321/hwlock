"""hwlock GUI: step 1 pick hardware, step 2 pick a program and lock them together.

Requires:  py -m pip install customtkinter
Run with:  py gui.py      (or  pyw gui.py  to hide the console window)
"""
import os
import queue
import threading
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from devices import list_devices
from lock import BLOCKABLE, DEFAULT_BLOCK, FocusLock
from windows import list_windows

KEY_LABELS = {"win": "Win", "alttab": "Alt+Tab", "altesc": "Alt+Esc", "ctrlesc": "Ctrl+Esc", "apps": "Menu key"}

# (light, dark) color pairs
ROW = ("#f1f3f6", "#2a2d33")
ROW_HOVER = ("#e3e7ee", "#33373e")
ROW_ACTIVE = ("#dbe8fb", "#203550")
MUTED = ("#6b7280", "#9aa1ab")
GREEN, GREEN_HOVER = "#2e9d57", "#257f47"
RED, RED_HOVER = "#d64545", "#b33939"
BADGE = {"keyboard": ("#3b82f6", "Keyboard"), "mouse": ("#a855f7", "Mouse"), "hid": ("#64748b", "HID")}
STATUS = {"idle": (("#e5e7eb", "#3a3d44"), MUTED, "Not locked"),
          "locked": (("#d6f5e1", "#1d3b2a"), ("#1f7a43", "#5fd38d"), "Locked"),
          "paused": (("#fdf0d5", "#43361a"), ("#9a6700", "#f2c45a"), "Paused")}


def font(size=13, weight="normal"):
    return ctk.CTkFont(family="Segoe UI", size=size, weight=weight)


class ClickRow(ctk.CTkFrame):
    """A rounded list row that highlights on hover and calls on_click anywhere inside it."""

    def __init__(self, master, on_click):
        super().__init__(master, fg_color=ROW, corner_radius=10)
        self.on_click = on_click
        self.active = False
        self.enabled = True

    def wire(self):
        """Bind click/hover on the row and every CTk widget nested inside it.

        Checkboxes/radios are skipped for clicks: they already toggle themselves, and
        also running on_click would toggle them straight back (net: no change)."""
        def walk(widget):
            if not isinstance(widget, ctk.CTkBaseClass):
                return   # tkinter internals (canvases/labels) are bound via their CTk owner
            if not isinstance(widget, (ctk.CTkCheckBox, ctk.CTkRadioButton)):
                widget.bind("<Button-1>", lambda _e: self.enabled and self.on_click(), add="+")
            widget.bind("<Enter>", lambda _e: self._paint(hover=True), add="+")
            widget.bind("<Leave>", lambda _e: self._paint(hover=False), add="+")
            if isinstance(widget, ctk.CTkFrame):
                for child in widget.winfo_children():
                    walk(child)
        walk(self)

    def set_active(self, active):
        self.active = active
        self._paint()

    def _paint(self, hover=False):
        self.configure(fg_color=ROW_ACTIVE if self.active else ROW_HOVER if hover and self.enabled else ROW)


class Header(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        ctk.CTkLabel(self, text="hwlock", font=font(22, "bold")).pack(side="left")
        ctk.CTkLabel(self, text="  lock your hardware to one app", font=font(13), text_color=MUTED).pack(side="left", pady=(6, 0))
        steps = ctk.CTkFrame(self, fg_color="transparent")
        steps.pack(side="right")
        self.chips = []
        for i, text in enumerate(("1  Hardware", "2  Program")):
            chip = ctk.CTkLabel(steps, text=text, font=font(12, "bold"), corner_radius=12, height=26, width=110)
            chip.pack(side="left", padx=(6 if i else 0, 0))
            self.chips.append(chip)
        self.set_step(0)

    def set_step(self, step):
        for i, chip in enumerate(self.chips):
            on = i == step
            chip.configure(fg_color=("#3b82f6" if on else ("#e5e7eb", "#3a3d44")),
                           text_color=("white" if on else MUTED))


class DevicePage(ctk.CTkFrame):
    """Step 1: list connected devices, tick some, press Select."""

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.rows = []   # (device, BooleanVar, ClickRow)

        ctk.CTkLabel(self, text="Select hardware", font=font(17, "bold")).pack(anchor="w")
        ctk.CTkLabel(self, text="Choose the keyboards and mice you want to lock, then press Select.",
                     font=font(13), text_color=MUTED).pack(anchor="w", pady=(0, 10))

        self.list = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.list.pack(fill="both", expand=True)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", pady=(12, 0))
        ctk.CTkButton(bar, text="↻  Refresh", width=110, fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=self.refresh).pack(side="left")
        self.count = ctk.CTkLabel(bar, text="", font=font(13), text_color=MUTED)
        self.count.pack(side="left", padx=14)
        ctk.CTkButton(bar, text="Select  →", width=130, height=36, font=font(14, "bold"),
                      command=self._select).pack(side="right")

        self.refresh()

    def refresh(self):
        for child in self.list.winfo_children():
            child.destroy()
        self.rows.clear()
        devices = list_devices()
        if not devices:
            ctk.CTkLabel(self.list, text="No external keyboards or mice found.", text_color=MUTED).pack(pady=20)
        for d in devices:
            var = tk.BooleanVar()
            row = ClickRow(self.list, on_click=lambda v=var: (v.set(not v.get()), self._changed()))
            row.pack(fill="x", pady=4, padx=(0, 6))
            ctk.CTkCheckBox(row, text="", width=24, variable=var, command=self._changed).pack(side="left", padx=(14, 4), pady=12)
            color, label = BADGE.get(d.kind, BADGE["hid"])
            ctk.CTkLabel(row, text=label, font=font(11, "bold"), fg_color=color, text_color="white",
                         corner_radius=8, width=74, height=22).pack(side="left", padx=(0, 12))
            text = ctk.CTkFrame(row, fg_color="transparent")
            text.pack(side="left", fill="x", expand=True, pady=8)
            ctk.CTkLabel(text, text=d.name, font=font(14, "bold"), anchor="w").pack(fill="x")
            # skip manufacturers that just repeat the name or are driver placeholders like "(Standard keyboards)"
            show_maker = d.manufacturer and d.manufacturer != d.name and not d.manufacturer.startswith("(")
            sub = d.connection + (f"  ·  {d.manufacturer}" if show_maker else "")
            ctk.CTkLabel(text, text=sub, font=font(12), text_color=MUTED, anchor="w").pack(fill="x")
            row.wire()
            self.rows.append((d, var, row))
        self._changed()

    def _changed(self):
        n = 0
        for _d, var, row in self.rows:
            row.set_active(var.get())
            n += var.get()
        self.count.configure(text=f"{n} selected" if n else "Nothing selected")

    def _select(self):
        selected = [d for d, var, _row in self.rows if var.get()]
        if not selected:
            messagebox.showwarning("hwlock", "Select at least one device first.")
            return
        self.app.show_programs(selected)


class ProgramPage(ctk.CTkFrame):
    """Step 2: show running programs and lock the selected hardware to one."""

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.selected = []
        self.programs = {}    # key -> AppWindow
        self.rows = {}        # key -> ClickRow
        self.radios = []
        self.choice = tk.StringVar()
        self.lock = None
        self.lock_thread = None
        self.log_queue = queue.Queue()

        ctk.CTkLabel(self, text="Choose a program", font=font(17, "bold")).pack(anchor="w")
        self.summary = ctk.CTkFrame(self, fg_color="transparent")
        self.summary.pack(fill="x", pady=(2, 10))

        self.list = ctk.CTkScrollableFrame(self, fg_color="transparent", height=200)
        self.list.pack(fill="both", expand=True)

        opts = ctk.CTkFrame(self, corner_radius=10)
        opts.pack(fill="x", pady=(12, 0))
        self.refocus_var = tk.BooleanVar(value=True)
        ctk.CTkSwitch(opts, text="Pull the program back to the front if something steals focus",
                      variable=self.refocus_var, font=font(13)).pack(anchor="w", padx=14, pady=(12, 6))
        keys = ctk.CTkFrame(opts, fg_color="transparent")
        keys.pack(anchor="w", padx=14, pady=(0, 12))
        ctk.CTkLabel(keys, text="Block keys:", font=font(13), text_color=MUTED).pack(side="left", padx=(0, 8))
        self.block_vars, self.key_boxes = {}, []
        for name in BLOCKABLE:
            var = tk.BooleanVar(value=name in DEFAULT_BLOCK)
            box = ctk.CTkCheckBox(keys, text=KEY_LABELS[name], variable=var, width=20, font=font(13),
                                  checkbox_width=20, checkbox_height=20)
            box.pack(side="left", padx=(0, 12))
            self.block_vars[name] = var
            self.key_boxes.append(box)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", pady=(12, 0))
        self.back_btn = ctk.CTkButton(bar, text="←  Back", width=90, fg_color="transparent", border_width=1,
                                      text_color=("gray10", "gray90"), command=app.show_devices)
        self.back_btn.pack(side="left")
        self.refresh_btn = ctk.CTkButton(bar, text="↻  Refresh", width=100, fg_color="transparent", border_width=1,
                                         text_color=("gray10", "gray90"), command=self.refresh)
        self.refresh_btn.pack(side="left", padx=8)
        self.status = ctk.CTkLabel(bar, text="", font=font(12, "bold"), corner_radius=12, height=28, width=150)
        self.status.pack(side="left", padx=8)
        self.lock_btn = ctk.CTkButton(bar, text="\U0001F512  Lock", width=140, height=38, font=font(15, "bold"),
                                      fg_color=GREEN, hover_color=GREEN_HOVER, command=self.toggle_lock)
        self.lock_btn.pack(side="right")

        ctk.CTkLabel(self, text="While locked:  Ctrl+Shift+F11 pause / resume   •   Ctrl+Shift+F12 unlock",
                     font=font(12), text_color=MUTED).pack(anchor="e", pady=(6, 0))
        self.log_box = ctk.CTkTextbox(self, height=90, font=ctk.CTkFont(family="Consolas", size=12),
                                      corner_radius=10, state="disabled")
        self.log_box.pack(fill="x", pady=(6, 0))

        self._set_status("idle")
        self.after(100, self._poll)

    # ----------------------------------------------------------------------
    def set_hardware(self, devices):
        self.selected = devices
        for child in self.summary.winfo_children():
            child.destroy()
        ctk.CTkLabel(self.summary, text="Locking", font=font(13), text_color=MUTED).pack(side="left", padx=(0, 6))
        for d in devices:
            color, _label = BADGE.get(d.kind, BADGE["hid"])
            ctk.CTkLabel(self.summary, text=d.name, font=font(12, "bold"), fg_color=color, text_color="white",
                         corner_radius=10, height=24).pack(side="left", padx=3)
        has_keyboard = any(d.kind == "keyboard" for d in devices)
        for box in self.key_boxes:
            box.configure(state="normal" if has_keyboard else "disabled")
        self.refresh()

    def refresh(self):
        prev = self.programs.get(self.choice.get())
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
            ctk.CTkLabel(text, text=p.exe, font=font(14, "bold"), anchor="w").pack(fill="x")
            ctk.CTkLabel(text, text=p.title[:80], font=font(12), text_color=MUTED, anchor="w").pack(fill="x")
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

    def locked(self):
        return self.lock_thread is not None and self.lock_thread.is_alive()

    def toggle_lock(self):
        if self.locked():
            self.lock.stop()
            return
        program = self.programs.get(self.choice.get())
        if not program:
            messagebox.showwarning("hwlock", "Choose a program from the list.")
            return
        has_keyboard = any(d.kind == "keyboard" for d in self.selected)
        has_mouse = any(d.kind == "mouse" for d in self.selected)
        block = [k for k, v in self.block_vars.items() if v.get()] if has_keyboard else []

        self.lock = FocusLock(process=program.exe, block=block, refocus=self.refocus_var.get(),
                              clip_mouse=has_mouse, log=self.log_queue.put)
        self.lock_thread = threading.Thread(target=self._run_lock, daemon=True)
        self.lock_thread.start()

        self._log(f"Locking {', '.join(d.name for d in self.selected)} → {program.exe}")
        self._set_locked_ui(True, program.exe)

    def _run_lock(self):
        try:
            self.lock.run()
        except Exception as e:  # surface errors in the log instead of dying silently
            self.log_queue.put(f"[error] {e}")

    def _set_status(self, kind, detail=""):
        bg, fg, text = STATUS[kind]
        self.status.configure(text=f"●  {text}{detail}", fg_color=bg, text_color=fg)

    def _set_locked_ui(self, locked, exe=""):
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

    def _log(self, text):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _poll(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get_nowait()
            self._log(msg)
            if "PAUSED" in msg:
                self._set_status("paused")
            elif "RESUMED" in msg:
                self._set_status("locked")
        if self.lock_thread is not None and not self.lock_thread.is_alive():
            self.lock_thread = None
            self._set_locked_ui(False)
        self.after(100, self._poll)

    def shutdown(self):
        if self.locked():
            self.lock.stop()
            self.lock_thread.join(timeout=1)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("hwlock")
        self.geometry("780x680")
        self.minsize(680, 580)

        self.header = Header(self)
        self.header.pack(fill="x", padx=20, pady=(16, 10))
        ctk.CTkFrame(self, height=1, fg_color=("#e5e7eb", "#34373d")).pack(fill="x", padx=20)

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=20, pady=(14, 18))
        self.device_page = DevicePage(self.body, self)
        self.program_page = ProgramPage(self.body, self)
        self.show_devices()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def show_devices(self):
        self.program_page.pack_forget()
        self.device_page.pack(fill="both", expand=True)
        self.header.set_step(0)

    def show_programs(self, devices):
        self.device_page.pack_forget()
        self.program_page.set_hardware(devices)
        self.program_page.pack(fill="both", expand=True)
        self.header.set_step(1)

    def _on_close(self):
        self.program_page.shutdown()
        self.destroy()


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    App().mainloop()
