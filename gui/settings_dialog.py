"""SettingsDialog — change the global keyboard shortcuts and the startup pop-up.

Opened from the gear button in the header. Each action has a button showing its current
shortcut; click it, then press the new combination (Esc cancels). Shortcuts are checked
with core.settings (must include Ctrl, no duplicates, nothing reserved) and saved to
%APPDATA%\\hwlock\\settings.json. They take effect the next time Lock or Notes mode starts,
and can't be changed while one is running (its keyboard hook would catch the keys).
The "Don't show the shortcuts pop-up" checkbox is the same choice as the one in the
WelcomeDialog shown at launch, and can be changed at any time.
"""
import customtkinter as ctk

from core import win32 as w
from core.settings import (ACTIONS, MODIFIER_VKS, Hotkey, default_hotkeys, problem, save_hide_welcome,
                           save_hotkeys, validate)
from gui.theme import MUTED, RED, ROW, ROW_HOVER, font

RECORDING, RECORDING_HOVER = "#3b82f6", "#2563eb"


class SettingsDialog(ctk.CTkToplevel):
    """Modal settings window. `on_save(hotkeys, hide_welcome)` is called after a successful save."""

    def __init__(self, app, hotkeys, hide_welcome, on_save, busy=False):
        super().__init__(app)
        self.title("hwlock settings")
        self.geometry("520x460")
        self.resizable(False, False)
        self.transient(app)               # stays above the main window
        self.on_save = on_save
        self.busy = busy                  # a lock or notes mode is running: read-only
        self.current = dict(hotkeys)      # what's in use now (kept as is while busy)
        self.pending = dict(hotkeys)      # edits, applied on Save
        self.hide_welcome = ctk.BooleanVar(value=hide_welcome)
        self._saved_hide = hide_welcome
        self.recording = None             # action whose button is waiting for a key press
        self.buttons = {}

        ctk.CTkLabel(self, text="Keyboard shortcuts", font=font(17, "bold")).pack(anchor="w", padx=20, pady=(18, 2))
        ctk.CTkLabel(
            self,
            text="These work from any window while Lock or Notes mode is running. "
                 "Click a shortcut, then press the new keys. Each must include Ctrl.",
            font=font(12), text_color=MUTED, wraplength=480, justify="left", anchor="w",
        ).pack(anchor="w", fill="x", padx=20, pady=(0, 12))

        rows = ctk.CTkFrame(self, fg_color="transparent")
        rows.pack(fill="x", padx=20)
        rows.grid_columnconfigure(0, weight=1)
        for i, (action, (_default, desc)) in enumerate(ACTIONS.items()):
            ctk.CTkLabel(rows, text=desc, font=font(13), anchor="w").grid(row=i, column=0, sticky="w", pady=5)
            btn = ctk.CTkButton(
                rows, width=200, height=34, font=font(13, "bold"),
                command=lambda a=action: self._start_recording(a),
            )
            btn.grid(row=i, column=1, sticky="e", pady=5)
            self.buttons[action] = btn

        self.message = ctk.CTkLabel(self, text="", font=font(12), wraplength=480, justify="left", anchor="w")
        self.message.pack(anchor="w", fill="x", padx=20, pady=(10, 0))

        ctk.CTkLabel(self, text="Startup", font=font(15, "bold")).pack(anchor="w", padx=20, pady=(14, 4))
        ctk.CTkCheckBox(
            self, text="Don't show the shortcuts pop-up when hwlock starts",
            variable=self.hide_welcome, font=font(13),
        ).pack(anchor="w", padx=20)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(side="bottom", fill="x", padx=20, pady=(0, 18))
        self.reset_btn = ctk.CTkButton(
            bar, text="Reset to defaults", width=140, fg_color="transparent", border_width=1,
            text_color=("gray10", "gray90"), command=self._reset,
        )
        self.reset_btn.pack(side="left")
        self.save_btn = ctk.CTkButton(bar, text="Save", width=100, font=font(13, "bold"), command=self._save)
        self.save_btn.pack(side="right")
        ctk.CTkButton(
            bar, text="Cancel", width=90, fg_color="transparent", border_width=1,
            text_color=("gray10", "gray90"), command=self.destroy,
        ).pack(side="right", padx=8)

        self.bind("<KeyPress>", self._on_key)
        self._paint()
        if busy:   # the startup checkbox and Save stay usable
            for widget in (*self.buttons.values(), self.reset_btn):
                widget.configure(state="disabled")
            self._say("Stop Lock or Notes mode to change shortcuts.", error=False)

        # Modal: keep input in this window until it closes.
        self.after(50, self._grab)

    def _grab(self):
        try:
            self.lift()
            self.focus_force()
            self.grab_set()
        except Exception:   # the window may already be gone (e.g. closed very quickly)
            pass

    # ------------------------------------------------------------------
    def _paint(self):
        """Show each pending shortcut on its button, highlighting the one being recorded."""
        for action, btn in self.buttons.items():
            if action == self.recording:
                btn.configure(text="Press keys…  (Esc cancels)", fg_color=RECORDING,
                              hover_color=RECORDING_HOVER, text_color="white")
            else:
                btn.configure(text=str(self.pending[action]), fg_color=ROW,
                              hover_color=ROW_HOVER, text_color=("gray10", "gray90"))

    def _say(self, text, error=True):
        self.message.configure(text=text, text_color=RED if error else MUTED)

    def _start_recording(self, action):
        self.recording = action
        self._say("")
        self._paint()
        self.focus_force()

    def _on_key(self, event):
        """While recording: modifiers alone wait for the key; Esc cancels; anything else
        becomes the new shortcut (if it's valid)."""
        if not self.recording:
            return None
        vk = event.keycode   # on Windows, Tk's keycode is the virtual-key code
        if vk in MODIFIER_VKS:
            return "break"
        held = w.key_down    # read Ctrl/Shift/Alt straight from Windows (no hooks run now)
        if vk == w.VK_ESCAPE and not (held(w.VK_CONTROL) or held(w.VK_SHIFT) or held(w.VK_MENU)):
            self.recording = None
            self._paint()
            return "break"
        hk = Hotkey(vk, held(w.VK_CONTROL), held(w.VK_SHIFT), held(w.VK_MENU))
        err = problem(hk)
        if err:
            self._say(f"{hk}: {err}")
        else:
            self.pending[self.recording] = hk
            self.recording = None
            clash = validate(self.pending)
            self._say(clash or "")
        self._paint()
        return "break"   # don't let Tk act on the keys (e.g. Ctrl+Tab focus moves)

    def _reset(self):
        self.recording = None
        self.pending = default_hotkeys()
        self._say("Defaults restored. Press Save to keep them.", error=False)
        self._paint()

    def _save(self):
        self.recording = None
        self._paint()
        hide = bool(self.hide_welcome.get())
        try:
            hotkeys = self.current if self.busy else self.pending   # read-only while a mode runs
            if hotkeys != self.current:
                save_hotkeys(hotkeys)
            if hide != self._saved_hide:
                save_hide_welcome(hide)
        except ValueError as e:
            self._say(str(e))
            return
        except OSError as e:
            self._say(f"Couldn't save settings: {e}")
            return
        self.on_save(dict(hotkeys), hide)
        self.destroy()
