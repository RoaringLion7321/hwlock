"""WelcomeDialog — the shortcuts pop-up shown when hwlock starts.

Lists the global keyboard shortcuts and what each one does. A "Don't show this again"
checkbox hides it on later launches; the same choice is in the Settings dialog.
The App decides whether to show it (core.settings.load_hide_welcome).
"""
import customtkinter as ctk

from core.settings import ACTIONS
from gui.theme import MUTED, ROW, font

# What each shortcut does, in more detail than the short labels in core.settings.ACTIONS.
DETAILS = {
    "notes_toggle": "Turns notes mode on or off. While it's on, everything you type goes into "
                    "the editor you picked, even when another window is in front.",
    "lock_pause":   "Pauses the lock so you can use other windows for a moment. "
                    "Press it again to lock again.",
    "stop":         "Ends the lock or notes mode completely and brings the hwlock window back.",
}


class WelcomeDialog(ctk.CTkToplevel):
    """`on_close(hide)` is called once, with the checkbox state, when the pop-up closes.
    `on_settings()` opens the Settings dialog (after this pop-up has closed)."""

    def __init__(self, app, hotkeys, hide, on_close, on_settings):
        super().__init__(app)
        self.title("hwlock shortcuts")
        self.geometry("540x430")
        self.resizable(False, False)
        self.transient(app)
        self.on_close = on_close
        self.on_settings = on_settings
        self.hide = ctk.BooleanVar(value=hide)

        ctk.CTkLabel(self, text="Keyboard shortcuts", font=font(17, "bold")).pack(anchor="w", padx=20, pady=(18, 2))
        ctk.CTkLabel(
            self,
            text="These work from any window while Lock or Notes mode is running.",
            font=font(12), text_color=MUTED, wraplength=500, justify="left", anchor="w",
        ).pack(anchor="w", fill="x", padx=20, pady=(0, 10))

        rows = ctk.CTkFrame(self, fg_color="transparent")
        rows.pack(fill="x", padx=20)
        rows.grid_columnconfigure(1, weight=1)
        for i, (action, (_default, label)) in enumerate(ACTIONS.items()):
            ctk.CTkLabel(
                rows, text=str(hotkeys[action]), font=font(13, "bold"), fg_color=ROW,
                corner_radius=8, width=150, height=30,
            ).grid(row=i, column=0, sticky="nw", padx=(0, 14), pady=6)
            text = ctk.CTkFrame(rows, fg_color="transparent")
            text.grid(row=i, column=1, sticky="ew", pady=6)
            ctk.CTkLabel(text, text=label, font=font(13, "bold"), anchor="w").pack(fill="x")
            ctk.CTkLabel(
                text, text=DETAILS[action], font=font(12), text_color=MUTED,
                wraplength=330, justify="left", anchor="w",
            ).pack(fill="x")

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(side="bottom", fill="x", padx=20, pady=(0, 18))
        ctk.CTkCheckBox(bar, text="Don't show this again", variable=self.hide, font=font(12)).pack(side="left")
        ctk.CTkButton(bar, text="OK", width=90, font=font(13, "bold"), command=self.close).pack(side="right")
        ctk.CTkButton(
            bar, text="Change shortcuts…", width=140, fg_color="transparent", border_width=1,
            text_color=("gray10", "gray90"), command=self._open_settings,
        ).pack(side="right", padx=8)

        ctk.CTkLabel(
            self, text="You can turn this pop-up back on in Settings (⚙).",
            font=font(11), text_color=MUTED, anchor="w",
        ).pack(side="bottom", anchor="w", padx=20, pady=(0, 8))

        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Return>", lambda _e: self.close())
        self.bind("<Escape>", lambda _e: self.close())
        self.after(50, self._grab)

    def _grab(self):
        try:
            self.lift()
            self.focus_force()
            self.grab_set()
        except Exception:   # the window may already be gone
            pass

    def close(self):
        hide = bool(self.hide.get())
        self.destroy()
        self.on_close(hide)

    def _open_settings(self):
        self.close()
        self.on_settings()
