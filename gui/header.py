"""Header bar: hwlock title, Lock / Notes mode toggle, step breadcrumbs, settings button."""
import customtkinter as ctk

from gui.theme import MUTED, font


class Header(ctk.CTkFrame):
    """Top bar with the app title, mode switcher (Lock/Notes), step chips and a settings gear."""

    def __init__(self, master, on_mode, on_settings):
        super().__init__(master, fg_color="transparent")

        ctk.CTkLabel(self, text="hwlock", font=font(22, "bold")).pack(side="left")

        self.mode = ctk.CTkSegmentedButton(
            self, values=["Lock", "Notes"], font=font(13, "bold"), command=on_mode
        )
        self.mode.set("Lock")
        self.mode.pack(side="left", padx=(16, 0), pady=(4, 0))

        # Packed before the steps so it stays rightmost when the steps are hidden / re-shown.
        ctk.CTkButton(
            self, text="⚙", width=34, height=30, font=font(17), fg_color="transparent",
            border_width=1, text_color=("gray10", "gray90"), command=on_settings,
        ).pack(side="right", padx=(10, 0))

        self.steps = steps = ctk.CTkFrame(self, fg_color="transparent")
        steps.pack(side="right")
        self.chips = []
        for i, text in enumerate(("1  Hardware", "2  Program")):
            chip = ctk.CTkLabel(
                steps, text=text, font=font(12, "bold"),
                corner_radius=12, height=26, width=110,
            )
            chip.pack(side="left", padx=(6 if i else 0, 0))
            self.chips.append(chip)
        self.set_step(0)

    def show_steps(self, visible: bool):
        """Show or hide the step breadcrumb chips (hidden on the Notes tab)."""
        if visible:
            self.steps.pack(side="right")
        else:
            self.steps.pack_forget()

    def set_step(self, step: int):
        """Highlight the active step chip (0 = Hardware, 1 = Program)."""
        for i, chip in enumerate(self.chips):
            on = i == step
            chip.configure(
                fg_color="#3b82f6" if on else ("#e5e7eb", "#3a3d44"),
                text_color="white"  if on else MUTED,
            )
