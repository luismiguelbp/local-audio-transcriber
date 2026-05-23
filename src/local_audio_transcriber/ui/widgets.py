"""Reusable UI widgets."""

from pathlib import Path
from typing import Callable

import customtkinter as ctk

from .theme import (
    CARD_FG_COLOR,
    ERROR_TEXT_COLOR,
    MUTED_TEXT_COLOR,
    PRIMARY_BUTTON_FG_COLOR,
    PRIMARY_TEXT_COLOR,
    PROCESSING_TEXT_COLOR,
    SECONDARY_BUTTON_FG_COLOR,
    SECONDARY_BUTTON_HOVER_COLOR,
    SECONDARY_BUTTON_TEXT_COLOR,
    SUCCESS_TEXT_COLOR,
)


class FileItem(ctk.CTkFrame):
    """A single file item in the queue."""

    def __init__(self, master, file_path: str, on_remove: Callable, **kwargs):
        super().__init__(master, **kwargs)

        self.file_path = file_path
        self.on_remove = on_remove
        self.status = "pending"

        self.configure(fg_color=CARD_FG_COLOR, corner_radius=8)

        self.name_label = ctk.CTkLabel(
            self,
            text=Path(file_path).name,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=PRIMARY_TEXT_COLOR,
            anchor="w",
        )
        self.name_label.grid(row=0, column=0, padx=12, pady=(8, 2), sticky="w")

        self.status_label = ctk.CTkLabel(
            self,
            text="Pending",
            font=ctk.CTkFont(size=11),
            text_color=MUTED_TEXT_COLOR,
            anchor="w",
        )
        self.status_label.grid(row=1, column=0, padx=12, pady=(0, 4), sticky="w")

        self.progress_bar = ctk.CTkProgressBar(
            self,
            height=6,
            corner_radius=3,
            progress_color=PRIMARY_BUTTON_FG_COLOR,
        )
        self.progress_bar.grid(row=2, column=0, columnspan=2, padx=12, pady=(0, 8), sticky="ew")
        self.progress_bar.set(0)

        self.remove_btn = ctk.CTkButton(
            self,
            text="✕",
            width=30,
            height=30,
            corner_radius=8,
            fg_color=SECONDARY_BUTTON_FG_COLOR,
            hover_color=SECONDARY_BUTTON_HOVER_COLOR,
            text_color=SECONDARY_BUTTON_TEXT_COLOR,
            command=self._remove,
        )
        self.remove_btn.grid(row=0, column=1, rowspan=2, padx=8, pady=4)

        self.grid_columnconfigure(0, weight=1)

    def _remove(self):
        if self.status != "processing":
            self.on_remove(self)

    def set_status(self, status: str, message: str = ""):
        """Update the status display."""
        self.status = status
        status_colors = {
            "pending": MUTED_TEXT_COLOR,
            "processing": PROCESSING_TEXT_COLOR,
            "complete": SUCCESS_TEXT_COLOR,
            "error": ERROR_TEXT_COLOR,
        }
        self.status_label.configure(
            text=message or status.capitalize(),
            text_color=status_colors.get(status, MUTED_TEXT_COLOR),
        )
        self.remove_btn.configure(state="disabled" if status == "processing" else "normal")

    def set_progress(self, value: float):
        """Set progress bar value (0.0 to 1.0)."""
        self.progress_bar.set(value)

