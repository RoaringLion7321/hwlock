"""ClickRow — a rounded list row that highlights on hover and fires on_click.

Shared by DevicePage, ProgramPage and NotesPage so it lives here rather than
in any single page module.
"""
import customtkinter as ctk

from gui.theme import ROW, ROW_ACTIVE, ROW_HOVER


class ClickRow(ctk.CTkFrame):
    """A rounded list row that highlights on hover and calls on_click anywhere inside it."""

    def __init__(self, master, on_click):
        super().__init__(master, fg_color=ROW, corner_radius=10)
        self.on_click = on_click
        self.active  = False
        self.enabled = True

    def wire(self):
        """Bind click/hover on the row and every CTk widget nested inside it.

        Checkboxes/radios are skipped for clicks: they already toggle themselves,
        and also running on_click would toggle them straight back (net: no change).
        """
        def walk(widget):
            if not isinstance(widget, ctk.CTkBaseClass):
                return   # tkinter internals (canvases/labels) are bound via their CTk owner
            if not isinstance(widget, (ctk.CTkCheckBox, ctk.CTkRadioButton)):
                widget.bind("<Button-1>", lambda _e: self.enabled and self.on_click(), add="+")
            widget.bind("<Enter>", lambda _e: self._paint(hover=True),  add="+")
            widget.bind("<Leave>", lambda _e: self._paint(hover=False), add="+")
            if isinstance(widget, ctk.CTkFrame):
                for child in widget.winfo_children():
                    walk(child)
        walk(self)

    def set_active(self, active: bool):
        self.active = active
        self._paint()

    def _paint(self, hover: bool = False):
        self.configure(
            fg_color=ROW_ACTIVE if self.active
                     else ROW_HOVER if hover and self.enabled
                     else ROW
        )
