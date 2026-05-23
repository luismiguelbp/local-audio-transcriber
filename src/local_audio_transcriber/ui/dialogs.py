"""Dialog windows and dialog-adjacent UI helpers."""

import os
import subprocess
import sys
from pathlib import Path
from tkinter import filedialog
from typing import Any

import customtkinter as ctk

from .theme import (
    APP_BG_COLOR,
    CONTROL_HEIGHT,
    HELPER_TEXT_SIZE,
    INPUT_BORDER_COLOR,
    INPUT_FG_COLOR,
    MUTED_TEXT_COLOR,
    PRIMARY_BUTTON_FG_COLOR,
    PRIMARY_BUTTON_HOVER_COLOR,
    PRIMARY_TEXT_COLOR,
    SECONDARY_TEXT_COLOR,
    SECTION_HEADING_SIZE,
    SUCCESS_TEXT_COLOR,
    neutral_option_menu_style,
    secondary_button_style,
)


def open_directory(path: Path):
    """Open a directory in the OS file manager."""
    directory = Path(path).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("win"):
        os.startfile(str(directory))  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.run(["open", str(directory)], check=False)
        return
    subprocess.run(["xdg-open", str(directory)], check=False)


class SettingsDialog(ctk.CTkToplevel):
    """Settings dialog window."""

    def __init__(self, master, config: Any):
        super().__init__(master)

        self.config = config
        self.result = None

        self.title("Settings")
        self.geometry("660x470")
        self.resizable(False, False)
        self.configure(fg_color=APP_BG_COLOR)

        self.transient(master)
        self._position_over_master(master)
        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        self.grab_set()

        ctk.CTkLabel(
            self,
            text="Theme",
            font=ctk.CTkFont(size=SECTION_HEADING_SIZE, weight="bold"),
            text_color=PRIMARY_TEXT_COLOR,
        ).pack(anchor="w", padx=20, pady=(18, 6))
        self.theme_var = ctk.StringVar(value=config.theme)
        self.theme_menu = ctk.CTkOptionMenu(
            self,
            values=["System", "White", "Dark"],
            variable=self.theme_var,
            width=200,
            **neutral_option_menu_style(),
        )
        self.theme_menu.pack(anchor="w", padx=20)

        ctk.CTkLabel(
            self,
            text="OpenAI",
            font=ctk.CTkFont(size=SECTION_HEADING_SIZE, weight="bold"),
            text_color=PRIMARY_TEXT_COLOR,
        ).pack(anchor="w", padx=20, pady=(22, 6))
        ctk.CTkLabel(
            self,
            text="Set the OS environment variable name that stores your OpenAI API key.",
            font=ctk.CTkFont(size=12),
            text_color=SECONDARY_TEXT_COLOR,
            wraplength=620,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 8))

        self.api_env_var_entry = ctk.CTkEntry(
            self,
            width=620,
            height=CONTROL_HEIGHT,
            corner_radius=8,
            fg_color=INPUT_FG_COLOR,
            border_color=INPUT_BORDER_COLOR,
            text_color=PRIMARY_TEXT_COLOR,
        )
        self.api_env_var_entry.pack(padx=20)
        self.api_env_var_entry.insert(0, config.api_key_env_var)

        env_var_name = config.api_key_env_var
        env_status = "Detected" if os.getenv(env_var_name, "").strip() else "Not detected"
        env_status_color = SUCCESS_TEXT_COLOR if env_status == "Detected" else MUTED_TEXT_COLOR
        ctk.CTkLabel(
            self,
            text=f"{env_status}: {env_var_name}",
            font=ctk.CTkFont(size=HELPER_TEXT_SIZE),
            text_color=env_status_color,
        ).pack(anchor="w", padx=20, pady=(5, 0))

        ctk.CTkLabel(
            self,
            text="Output directory",
            font=ctk.CTkFont(size=SECTION_HEADING_SIZE, weight="bold"),
            text_color=PRIMARY_TEXT_COLOR,
        ).pack(anchor="w", padx=20, pady=(22, 6))

        dir_frame = ctk.CTkFrame(self, fg_color="transparent")
        dir_frame.pack(fill="x", padx=20)

        self.output_dir_entry = ctk.CTkEntry(
            dir_frame,
            width=390,
            height=CONTROL_HEIGHT,
            corner_radius=8,
            fg_color=INPUT_FG_COLOR,
            border_color=INPUT_BORDER_COLOR,
            text_color=PRIMARY_TEXT_COLOR,
        )
        self.output_dir_entry.pack(side="left")
        self.output_dir_entry.insert(0, config.output_dir)

        ctk.CTkButton(
            dir_frame,
            text="Browse",
            width=70,
            **secondary_button_style(),
            command=self._browse_output_dir,
        ).pack(side="left", padx=(10, 0))
        ctk.CTkButton(
            dir_frame,
            text="Open",
            width=70,
            **secondary_button_style(),
            command=self._open_output_dir,
        ).pack(side="left", padx=(10, 0))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=28)

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=100,
            **secondary_button_style(),
            command=self.destroy,
        ).pack(side="right")

        ctk.CTkButton(
            btn_frame,
            text="Save",
            width=100,
            height=CONTROL_HEIGHT,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=PRIMARY_BUTTON_FG_COLOR,
            hover_color=PRIMARY_BUTTON_HOVER_COLOR,
            command=self._save,
        ).pack(side="right", padx=(0, 10))

    def _position_over_master(self, master):
        master.update_idletasks()
        self.update_idletasks()

        dialog_width = 660
        dialog_height = 470
        x = master.winfo_rootx() + (master.winfo_width() - dialog_width) // 2
        y = master.winfo_rooty() + (master.winfo_height() - dialog_height) // 2
        self.geometry(f"{dialog_width}x{dialog_height}+{max(0, x)}+{max(0, y)}")

    def _browse_output_dir(self):
        directory = filedialog.askdirectory(initialdir=self.output_dir_entry.get())
        if directory:
            self.output_dir_entry.delete(0, "end")
            self.output_dir_entry.insert(0, directory)

    def _open_output_dir(self):
        output_dir = Path(self.output_dir_entry.get().strip() or self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        open_directory(output_dir)

    def _save(self):
        self.config.theme = self.theme_var.get()
        self.config.api_key_env_var = self.api_env_var_entry.get().strip()
        self.config.output_dir = self.output_dir_entry.get().strip()
        self.result = True
        self.destroy()

