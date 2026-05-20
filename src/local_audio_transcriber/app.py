"""
Local Audio Transcriber

A desktop GUI application for transcribing audio files using OpenAI's Whisper API.
Handles long meeting recordings by automatically chunking files.
"""

import json
import logging
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Optional

import customtkinter as ctk
from dotenv import load_dotenv
from tkinterdnd2 import DND_FILES, TkinterDnD

from .live_recorder import (
    AudioDevice,
    LiveAudioRecorder,
    LiveAudioLevelMonitor,
    LiveRecorderError,
    device_labels,
    find_device_by_label,
    list_microphones,
    list_system_outputs,
)
from .streaming_transcriber import (
    ACCURATE_MODEL,
    DEFAULT_MODEL,
    RollingStreamingTranscriber,
)
from .logging_setup import setup_logging
from .transcriber import AudioTranscriber, TranscriptionError, save_transcription


# Load environment variables
load_dotenv()

# App configuration
APP_NAME = "Local Audio Transcriber"
CONFIG_FILE = Path.home() / ".local-transcriber" / "config.json"
SUPPORTED_EXTENSIONS = ('.mp3', '.wav', '.m4a', '.mp4', '.mkv', '.webm', '.ogg', '.flac')
logger = logging.getLogger(__name__)

APP_BG_COLOR = ("#f8fafc", "#0f172a")
CARD_FG_COLOR = ("#ffffff", "#1e293b")
DROP_ZONE_FG_COLOR = ("#f1f5f9", "#172033")
BORDER_COLOR = ("#cbd5e1", "#475569")
HOVER_COLOR = ("#e2e8f0", "#334155")
INPUT_FG_COLOR = ("#ffffff", "#111827")
INPUT_BORDER_COLOR = ("#cbd5e1", "#334155")
PRIMARY_TEXT_COLOR = ("#111827", "#f9fafb")
SECONDARY_TEXT_COLOR = ("#374151", "#d1d5db")
MUTED_TEXT_COLOR = ("#4b5563", "#9ca3af")
PROCESSING_TEXT_COLOR = ("#1d4ed8", "#60a5fa")
SUCCESS_TEXT_COLOR = ("#166534", "#4ade80")
ERROR_TEXT_COLOR = ("#b91c1c", "#f87171")
PRIMARY_BUTTON_FG_COLOR = ("#3B8ED0", "#1F6AA5")
PRIMARY_BUTTON_HOVER_COLOR = ("#36719F", "#144870")
SECONDARY_BUTTON_FG_COLOR = ("#e2e8f0", "#334155")
SECONDARY_BUTTON_HOVER_COLOR = ("#cbd5e1", "#475569")
SECONDARY_BUTTON_TEXT_COLOR = ("#111827", "#f9fafb")
DANGER_BUTTON_FG_COLOR = ("#b91c1c", "#dc2626")
DANGER_BUTTON_HOVER_COLOR = ("#991b1b", "#b91c1c")
LIVE_TRANSCRIPTION_SEGMENT_SECONDS = 10


class ConfigManager:
    """Manages application configuration."""
    
    def __init__(self):
        self.config_path = CONFIG_FILE
        self.config = self._load_config()
    
    def _load_config(self) -> dict:
        """Load configuration from file."""
        defaults = {
            'output_dir': str(Path.home() / 'Documents' / 'Transcriptions'),
            'theme': 'System',
            'api_key_env_var': 'OPENAI_API_KEY',
            'mic_device': '',
            'system_device': '',
            'transcription_model': DEFAULT_MODEL,
        }
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    loaded_config = json.load(f)
                loaded_config.pop('api_key', None)
                return {**defaults, **loaded_config}
            except (json.JSONDecodeError, IOError):
                logger.warning("Failed to read config file %s. Using defaults.", self.config_path)
                pass
        return defaults
    
    def save(self):
        """Save configuration to file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)
        logger.info("Configuration saved to %s", self.config_path)
    
    @property
    def output_dir(self) -> str:
        return self.config.get('output_dir', str(Path.home() / 'Documents' / 'Transcriptions'))
    
    @output_dir.setter
    def output_dir(self, value: str):
        self.config['output_dir'] = value
        self.save()

    @property
    def mic_device(self) -> str:
        return self.config.get('mic_device', '')

    @mic_device.setter
    def mic_device(self, value: str):
        self.config['mic_device'] = value
        self.save()

    @property
    def system_device(self) -> str:
        return self.config.get('system_device', '')

    @system_device.setter
    def system_device(self, value: str):
        self.config['system_device'] = value
        self.save()

    @property
    def transcription_model(self) -> str:
        return self.config.get('transcription_model', DEFAULT_MODEL)

    @transcription_model.setter
    def transcription_model(self, value: str):
        self.config['transcription_model'] = value
        self.save()

    @property
    def theme(self) -> str:
        value = str(self.config.get('theme', 'System')).strip().title()
        if value not in {"System", "White", "Dark"}:
            return "System"
        return value

    @theme.setter
    def theme(self, value: str):
        normalized = str(value).strip().title()
        if normalized not in {"System", "White", "Dark"}:
            normalized = "System"
        self.config['theme'] = normalized
        self.save()

    @property
    def api_key_env_var(self) -> str:
        value = str(self.config.get('api_key_env_var', 'OPENAI_API_KEY')).strip()
        return value or "OPENAI_API_KEY"

    @api_key_env_var.setter
    def api_key_env_var(self, value: str):
        normalized = str(value).strip() or "OPENAI_API_KEY"
        self.config['api_key_env_var'] = normalized
        self.save()

    def resolved_api_key(self) -> str:
        env_var = self.api_key_env_var
        if env_var:
            value = os.getenv(env_var, "").strip()
            if value:
                return value
        if env_var != "OPENAI_API_KEY":
            return os.getenv("OPENAI_API_KEY", "").strip()
        return ""


class FileItem(ctk.CTkFrame):
    """A single file item in the queue."""
    
    def __init__(self, master, file_path: str, on_remove: callable, **kwargs):
        super().__init__(master, **kwargs)
        
        self.file_path = file_path
        self.on_remove = on_remove
        self.status = "pending"
        
        self.configure(fg_color=CARD_FG_COLOR, corner_radius=8)
        
        # File name
        self.name_label = ctk.CTkLabel(
            self, 
            text=Path(file_path).name,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=PRIMARY_TEXT_COLOR,
            anchor="w"
        )
        self.name_label.grid(row=0, column=0, padx=12, pady=(8, 2), sticky="w")
        
        # Status label
        self.status_label = ctk.CTkLabel(
            self, 
            text="Pending",
            font=ctk.CTkFont(size=11),
            text_color=MUTED_TEXT_COLOR,
            anchor="w"
        )
        self.status_label.grid(row=1, column=0, padx=12, pady=(0, 4), sticky="w")
        
        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(
            self,
            height=6,
            corner_radius=3,
            progress_color=PRIMARY_BUTTON_FG_COLOR,
        )
        self.progress_bar.grid(row=2, column=0, columnspan=2, padx=12, pady=(0, 8), sticky="ew")
        self.progress_bar.set(0)
        
        # Remove button
        self.remove_btn = ctk.CTkButton(
            self, 
            text="✕", 
            width=30, 
            height=30,
            corner_radius=8,
            fg_color=SECONDARY_BUTTON_FG_COLOR,
            hover_color=SECONDARY_BUTTON_HOVER_COLOR,
            text_color=SECONDARY_BUTTON_TEXT_COLOR,
            command=self._remove
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
            text_color=status_colors.get(status, MUTED_TEXT_COLOR)
        )
        
        if status == "processing":
            self.remove_btn.configure(state="disabled")
        else:
            self.remove_btn.configure(state="normal")
    
    def set_progress(self, value: float):
        """Set progress bar value (0.0 to 1.0)."""
        self.progress_bar.set(value)


class SettingsDialog(ctk.CTkToplevel):
    """Settings dialog window."""
    
    def __init__(self, master, config: ConfigManager):
        super().__init__(master)
        
        self.config = config
        self.result = None
        
        self.title("Settings")
        self.geometry("560x450")
        self.resizable(False, False)
        self.configure(fg_color=APP_BG_COLOR)
        
        # Keep the dialog above the main window and centered over it.
        self.transient(master)
        self._position_over_master(master)
        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        self.grab_set()
        
        # Theme
        ctk.CTkLabel(
            self,
            text="Theme",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=PRIMARY_TEXT_COLOR,
        ).pack(
            anchor="w", padx=20, pady=(15, 5)
        )
        self.theme_var = ctk.StringVar(value=config.theme)
        self.theme_menu = ctk.CTkOptionMenu(
            self,
            values=["System", "White", "Dark"],
            variable=self.theme_var,
            width=180,
            height=34,
            corner_radius=8,
            fg_color=PRIMARY_BUTTON_FG_COLOR,
            button_color=PRIMARY_BUTTON_FG_COLOR,
            button_hover_color=PRIMARY_BUTTON_HOVER_COLOR,
            dropdown_fg_color=CARD_FG_COLOR,
            dropdown_hover_color=HOVER_COLOR,
            dropdown_text_color=PRIMARY_TEXT_COLOR,
        )
        self.theme_menu.pack(anchor="w", padx=20)

        # OpenAI
        ctk.CTkLabel(
            self,
            text="OpenAI",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=PRIMARY_TEXT_COLOR,
        ).pack(
            anchor="w", padx=20, pady=(20, 5)
        )
        ctk.CTkLabel(
            self,
            text="Set the OS environment variable name that stores your OpenAI API key.",
            font=ctk.CTkFont(size=12),
            text_color=SECONDARY_TEXT_COLOR,
            wraplength=500,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 8))

        self.api_env_var_entry = ctk.CTkEntry(
            self,
            width=460,
            height=34,
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
            font=ctk.CTkFont(size=11),
            text_color=env_status_color,
        ).pack(anchor="w", padx=20, pady=(5, 0))
        
        # Output Directory
        ctk.CTkLabel(
            self,
            text="Output directory",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=PRIMARY_TEXT_COLOR,
        ).pack(
            anchor="w", padx=20, pady=(20, 5)
        )
        
        dir_frame = ctk.CTkFrame(self, fg_color="transparent")
        dir_frame.pack(fill="x", padx=20)
        
        self.output_dir_entry = ctk.CTkEntry(
            dir_frame,
            width=300,
            height=34,
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
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(size=13),
            fg_color=SECONDARY_BUTTON_FG_COLOR,
            hover_color=SECONDARY_BUTTON_HOVER_COLOR,
            text_color=SECONDARY_BUTTON_TEXT_COLOR,
            command=self._browse_output_dir
        ).pack(side="left", padx=(10, 0))
        ctk.CTkButton(
            dir_frame,
            text="Open",
            width=70,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(size=13),
            fg_color=SECONDARY_BUTTON_FG_COLOR,
            hover_color=SECONDARY_BUTTON_HOVER_COLOR,
            text_color=SECONDARY_BUTTON_TEXT_COLOR,
            command=self._open_output_dir,
        ).pack(side="left", padx=(10, 0))
        
        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=30)
        
        ctk.CTkButton(
            btn_frame, 
            text="Cancel", 
            width=100,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(size=13),
            fg_color=SECONDARY_BUTTON_FG_COLOR,
            hover_color=SECONDARY_BUTTON_HOVER_COLOR,
            text_color=SECONDARY_BUTTON_TEXT_COLOR,
            command=self.destroy
        ).pack(side="right")
        
        ctk.CTkButton(
            btn_frame, 
            text="Save", 
            width=100,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=PRIMARY_BUTTON_FG_COLOR,
            hover_color=PRIMARY_BUTTON_HOVER_COLOR,
            command=self._save
        ).pack(side="right", padx=(0, 10))

    def _position_over_master(self, master):
        master.update_idletasks()
        self.update_idletasks()

        dialog_width = 560
        dialog_height = 450
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


class _DnDCTk(ctk.CTk, TkinterDnD.DnDWrapper):
    """ctk.CTk root window with tkinterdnd2 OS-level drag-and-drop support."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dnd_available = False
        try:
            self.TkdndVersion = TkinterDnD._require(self)
            self.dnd_available = True
        except RuntimeError as exc:
            logger.warning("Drag-and-drop unavailable: %s", exc)


class TranscriberApp(_DnDCTk):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        
        self.config = ConfigManager()
        self.file_items: list[FileItem] = []
        self.is_processing = False
        self.transcriber: Optional[AudioTranscriber] = None
        self.mic_devices: list[AudioDevice] = []
        self.system_devices: list[AudioDevice] = []
        self.live_recorder: Optional[LiveAudioRecorder] = None
        self.live_monitor: Optional[LiveAudioLevelMonitor] = None
        self.live_transcriber: Optional[RollingStreamingTranscriber] = None
        self.is_recording = False
        self.current_mode = "File Upload"
        self.live_transcript = ""
        self.live_audio_path: Optional[Path] = None
        self.live_transcript_path: Optional[Path] = None
        self._drag_leave_after: Optional[str] = None
        
        self._setup_window()
        self._create_widgets()
        self._setup_drag_drop()
        
        # Check for API key on startup
        if not self.config.resolved_api_key():
            self.after(500, self._prompt_api_key)
    
    def _setup_window(self):
        """Configure the main window."""
        self.title(APP_NAME)
        self.geometry("900x760")
        self.minsize(760, 620)
        self.configure(fg_color=APP_BG_COLOR)
        
        # Set appearance
        theme_map = {"System": "system", "White": "light", "Dark": "dark"}
        ctk.set_appearance_mode(theme_map.get(self.config.theme, "system"))
        ctk.set_default_color_theme("blue")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        """Stop audio resources before closing the app."""
        logger.info("Closing application.")
        self._stop_level_monitor()
        if self.is_recording:
            self.is_recording = False
            if self.live_recorder is not None:
                self.live_recorder.stop()
            if self.live_transcriber is not None:
                self.live_transcriber.stop(wait=False)
        self.destroy()
    
    def _create_widgets(self):
        """Create all UI widgets."""
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(20, 10))
        
        ctk.CTkLabel(
            header_frame, 
            text=APP_NAME,
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=PRIMARY_TEXT_COLOR,
        ).pack(side="left")
        
        ctk.CTkButton(
            header_frame, 
            text="Settings",
            width=92,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(size=13),
            fg_color=SECONDARY_BUTTON_FG_COLOR,
            hover_color=SECONDARY_BUTTON_HOVER_COLOR,
            text_color=SECONDARY_BUTTON_TEXT_COLOR,
            command=self._open_settings
        ).pack(side="right")
        ctk.CTkButton(
            header_frame,
            text="Output",
            width=92,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(size=13),
            fg_color=SECONDARY_BUTTON_FG_COLOR,
            hover_color=SECONDARY_BUTTON_HOVER_COLOR,
            text_color=SECONDARY_BUTTON_TEXT_COLOR,
            command=self._open_output_directory,
        ).pack(side="right", padx=(0, 10))

        self.mode_selector = ctk.CTkSegmentedButton(
            self,
            values=["File Upload", "Live Recording"],
            command=self._switch_mode,
            height=36,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=SECONDARY_BUTTON_FG_COLOR,
            selected_color=PRIMARY_BUTTON_FG_COLOR,
            selected_hover_color=PRIMARY_BUTTON_HOVER_COLOR,
            unselected_color=SECONDARY_BUTTON_FG_COLOR,
            unselected_hover_color=SECONDARY_BUTTON_HOVER_COLOR,
            text_color=SECONDARY_BUTTON_TEXT_COLOR,
        )
        self.mode_selector.pack(fill="x", padx=20, pady=(0, 10))
        self.mode_selector.set("File Upload")

        self.file_mode_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.live_mode_frame = ctk.CTkFrame(self, fg_color="transparent")

        self._create_file_upload_widgets()
        self._create_live_recording_widgets()
        self._switch_mode("File Upload")

        # Status bar
        self.status_label = ctk.CTkLabel(
            self,
            text="Ready",
            font=ctk.CTkFont(size=11),
            text_color=MUTED_TEXT_COLOR,
        )
        self.status_label.pack(pady=(0, 10))

    def _create_file_upload_widgets(self):
        """Create the existing file upload workflow."""
        # Drop zone
        self.drop_zone = ctk.CTkFrame(
            self.file_mode_frame,
            height=120,
            fg_color=DROP_ZONE_FG_COLOR,
            border_width=1,
            border_color=BORDER_COLOR,
            corner_radius=12
        )
        self.drop_zone.pack(fill="x", padx=20, pady=10)
        self.drop_zone.pack_propagate(False)
        
        drop_label_frame = ctk.CTkFrame(self.drop_zone, fg_color="transparent")
        drop_label_frame.place(relx=0.5, rely=0.5, anchor="center")
        
        ctk.CTkLabel(
            drop_label_frame,
            text="Drop audio files here",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=PRIMARY_TEXT_COLOR,
        ).pack()
        
        ctk.CTkLabel(
            drop_label_frame,
            text="or click the button below",
            font=ctk.CTkFont(size=12),
            text_color=SECONDARY_TEXT_COLOR,
        ).pack(pady=(5, 0))
        
        # Add files button
        ctk.CTkButton(
            self.file_mode_frame,
            text="+ Add Audio Files",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40,
            corner_radius=8,
            fg_color=PRIMARY_BUTTON_FG_COLOR,
            hover_color=PRIMARY_BUTTON_HOVER_COLOR,
            command=self._browse_files
        ).pack(pady=10)
        
        # Supported formats label
        ctk.CTkLabel(
            self.file_mode_frame,
            text=f"Supported formats: {', '.join(SUPPORTED_EXTENSIONS)}",
            font=ctk.CTkFont(size=11),
            text_color=MUTED_TEXT_COLOR,
        ).pack()
        
        # File queue frame
        queue_label = ctk.CTkLabel(
            self.file_mode_frame,
            text="File Queue",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=PRIMARY_TEXT_COLOR,
            anchor="w"
        )
        queue_label.pack(fill="x", padx=20, pady=(20, 5))
        
        # Scrollable queue container
        self.queue_frame = ctk.CTkScrollableFrame(
            self.file_mode_frame,
            fg_color="transparent",
            scrollbar_button_color=SECONDARY_BUTTON_FG_COLOR,
            scrollbar_button_hover_color=SECONDARY_BUTTON_HOVER_COLOR,
            corner_radius=0,
        )
        self.queue_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        
        # Empty queue message
        self.empty_label = ctk.CTkLabel(
            self.queue_frame,
            text="No files added yet",
            font=ctk.CTkFont(size=13),
            text_color=MUTED_TEXT_COLOR,
        )
        self.empty_label.pack(pady=40)
        
        # Bottom action bar
        action_frame = ctk.CTkFrame(self.file_mode_frame, fg_color="transparent")
        action_frame.pack(fill="x", padx=20, pady=(0, 20))
        
        self.clear_btn = ctk.CTkButton(
            action_frame, 
            text="Clear All",
            width=100,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(size=13),
            fg_color=SECONDARY_BUTTON_FG_COLOR,
            hover_color=SECONDARY_BUTTON_HOVER_COLOR,
            text_color=SECONDARY_BUTTON_TEXT_COLOR,
            command=self._clear_queue,
            state="disabled"
        )
        self.clear_btn.pack(side="left")
        
        self.transcribe_btn = ctk.CTkButton(
            action_frame, 
            text="Start Transcription",
            width=180,
            height=40,
            corner_radius=8,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=PRIMARY_BUTTON_FG_COLOR,
            hover_color=PRIMARY_BUTTON_HOVER_COLOR,
            command=self._start_transcription,
            state="disabled"
        )
        self.transcribe_btn.pack(side="right")

    def _create_live_recording_widgets(self):
        """Create the live recording workflow."""
        self.live_mode_frame.grid_columnconfigure(0, weight=1)

        device_frame = ctk.CTkFrame(self.live_mode_frame, fg_color=CARD_FG_COLOR, corner_radius=12)
        device_frame.pack(fill="x", padx=20, pady=(5, 10))
        device_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            device_frame,
            text="Live Recording",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=PRIMARY_TEXT_COLOR,
            anchor="w",
        ).grid(row=0, column=0, columnspan=3, sticky="ew", padx=15, pady=(15, 10))

        ctk.CTkLabel(
            device_frame,
            text="Microphone",
            text_color=SECONDARY_TEXT_COLOR,
            anchor="w",
        ).grid(
            row=1, column=0, sticky="w", padx=15, pady=6
        )
        self.mic_menu = ctk.CTkOptionMenu(
            device_frame,
            values=["Loading..."],
            height=34,
            corner_radius=8,
            fg_color=PRIMARY_BUTTON_FG_COLOR,
            button_color=PRIMARY_BUTTON_FG_COLOR,
            button_hover_color=PRIMARY_BUTTON_HOVER_COLOR,
            dropdown_fg_color=CARD_FG_COLOR,
            dropdown_hover_color=HOVER_COLOR,
            dropdown_text_color=PRIMARY_TEXT_COLOR,
        )
        self.mic_menu.grid(row=1, column=1, sticky="ew", padx=(0, 15), pady=6)

        ctk.CTkLabel(
            device_frame,
            text="System audio",
            text_color=SECONDARY_TEXT_COLOR,
            anchor="w",
        ).grid(
            row=2, column=0, sticky="w", padx=15, pady=6
        )
        self.system_menu = ctk.CTkOptionMenu(
            device_frame,
            values=["Loading..."],
            height=34,
            corner_radius=8,
            fg_color=PRIMARY_BUTTON_FG_COLOR,
            button_color=PRIMARY_BUTTON_FG_COLOR,
            button_hover_color=PRIMARY_BUTTON_HOVER_COLOR,
            dropdown_fg_color=CARD_FG_COLOR,
            dropdown_hover_color=HOVER_COLOR,
            dropdown_text_color=PRIMARY_TEXT_COLOR,
        )
        self.system_menu.grid(row=2, column=1, sticky="ew", padx=(0, 15), pady=6)

        ctk.CTkButton(
            device_frame,
            text="Refresh Devices",
            width=130,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(size=13),
            fg_color=SECONDARY_BUTTON_FG_COLOR,
            hover_color=SECONDARY_BUTTON_HOVER_COLOR,
            text_color=SECONDARY_BUTTON_TEXT_COLOR,
            command=self._refresh_audio_devices,
        ).grid(row=1, column=2, rowspan=2, sticky="ns", padx=(0, 15), pady=6)

        ctk.CTkLabel(
            device_frame,
            text="Model",
            text_color=SECONDARY_TEXT_COLOR,
            anchor="w",
        ).grid(
            row=3, column=0, sticky="w", padx=15, pady=6
        )
        self.model_menu = ctk.CTkOptionMenu(
            device_frame,
            values=[DEFAULT_MODEL, ACCURATE_MODEL],
            command=self._on_model_selected,
            height=34,
            corner_radius=8,
            fg_color=PRIMARY_BUTTON_FG_COLOR,
            button_color=PRIMARY_BUTTON_FG_COLOR,
            button_hover_color=PRIMARY_BUTTON_HOVER_COLOR,
            dropdown_fg_color=CARD_FG_COLOR,
            dropdown_hover_color=HOVER_COLOR,
            dropdown_text_color=PRIMARY_TEXT_COLOR,
        )
        self.model_menu.grid(row=3, column=1, sticky="ew", padx=(0, 15), pady=(6, 15))
        model_choice = self.config.transcription_model
        if model_choice not in (DEFAULT_MODEL, ACCURATE_MODEL):
            model_choice = DEFAULT_MODEL
        self.model_menu.set(model_choice)
        self.config.transcription_model = model_choice

        meter_frame = ctk.CTkFrame(self.live_mode_frame, fg_color=CARD_FG_COLOR, corner_radius=12)
        meter_frame.pack(fill="x", padx=20, pady=(0, 10))
        meter_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            meter_frame,
            text="Mic level",
            text_color=SECONDARY_TEXT_COLOR,
            anchor="w",
        ).grid(
            row=0, column=0, sticky="w", padx=15, pady=(15, 8)
        )
        self.mic_level_bar = ctk.CTkProgressBar(
            meter_frame,
            height=12,
            corner_radius=8,
            progress_color=PRIMARY_BUTTON_FG_COLOR,
        )
        self.mic_level_bar.grid(row=0, column=1, sticky="ew", padx=(0, 15), pady=(15, 8))
        self.mic_level_bar.set(0)

        ctk.CTkLabel(
            meter_frame,
            text="System level",
            text_color=SECONDARY_TEXT_COLOR,
            anchor="w",
        ).grid(
            row=1, column=0, sticky="w", padx=15, pady=(0, 15)
        )
        self.system_level_bar = ctk.CTkProgressBar(
            meter_frame,
            height=12,
            corner_radius=8,
            progress_color=PRIMARY_BUTTON_FG_COLOR,
        )
        self.system_level_bar.grid(row=1, column=1, sticky="ew", padx=(0, 15), pady=(0, 15))
        self.system_level_bar.set(0)

        control_frame = ctk.CTkFrame(self.live_mode_frame, fg_color="transparent")
        control_frame.pack(fill="x", padx=20, pady=(0, 10))

        self.record_btn = ctk.CTkButton(
            control_frame,
            text="Start Recording",
            width=180,
            height=40,
            corner_radius=8,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=PRIMARY_BUTTON_FG_COLOR,
            hover_color=PRIMARY_BUTTON_HOVER_COLOR,
            command=self._toggle_live_recording,
        )
        self.record_btn.pack(side="left")

        self.live_status_label = ctk.CTkLabel(
            control_frame,
            text="Select devices, then speak or play audio to test the meters.",
            font=ctk.CTkFont(size=12),
            text_color=SECONDARY_TEXT_COLOR,
            anchor="w",
        )
        self.live_status_label.pack(side="left", fill="x", expand=True, padx=15)

        transcript_header = ctk.CTkFrame(self.live_mode_frame, fg_color="transparent")
        transcript_header.pack(fill="x", padx=20, pady=(10, 5))

        ctk.CTkLabel(
            transcript_header,
            text="Live Transcript",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=PRIMARY_TEXT_COLOR,
            anchor="w",
        ).pack(side="left")

        ctk.CTkButton(
            transcript_header,
            text="Copy to Clipboard",
            width=150,
            height=32,
            corner_radius=8,
            font=ctk.CTkFont(size=13),
            fg_color=SECONDARY_BUTTON_FG_COLOR,
            hover_color=SECONDARY_BUTTON_HOVER_COLOR,
            text_color=SECONDARY_BUTTON_TEXT_COLOR,
            command=self._copy_live_transcript_to_clipboard,
        ).pack(side="right")

        self.transcript_box = ctk.CTkTextbox(
            self.live_mode_frame,
            height=220,
            wrap="word",
            corner_radius=12,
            border_width=1,
            border_color=BORDER_COLOR,
            fg_color=CARD_FG_COLOR,
            text_color=PRIMARY_TEXT_COLOR,
        )
        self.transcript_box.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.transcript_box.insert("1.0", "Transcript will appear here while recording.\n")
        self.transcript_box.configure(state="disabled")

        self._refresh_audio_devices()

    def _switch_mode(self, mode: str):
        """Switch between file upload and live recording views."""
        self.current_mode = mode
        self.file_mode_frame.pack_forget()
        self.live_mode_frame.pack_forget()

        if mode == "Live Recording":
            self.live_mode_frame.pack(fill="both", expand=True)
            self._restart_level_monitor()
        else:
            self._stop_level_monitor()
            self.file_mode_frame.pack(fill="both", expand=True)

    def _refresh_audio_devices(self):
        """Refresh selectable recording devices."""
        try:
            self.mic_devices = list_microphones()
            self.system_devices = list_system_outputs()
            logger.info(
                "Audio devices refreshed (microphones=%s, system_outputs=%s)",
                len(self.mic_devices),
                len(self.system_devices),
            )
        except Exception as e:
            logger.exception("Could not list audio devices.")
            messagebox.showerror("Audio Devices", f"Could not list audio devices:\n{e}")
            self.mic_devices = []
            self.system_devices = []

        mic_values = device_labels(self.mic_devices) or ["No microphones found"]
        system_values = ["None"] + device_labels(self.system_devices)

        self.mic_menu.configure(values=mic_values, command=self._on_mic_selected)
        self.system_menu.configure(values=system_values, command=self._on_system_selected)

        mic_choice = self.config.mic_device if self.config.mic_device in mic_values else mic_values[0]
        system_choice = self.config.system_device if self.config.system_device in system_values else system_values[0]
        self.mic_menu.set(mic_choice)
        self.system_menu.set(system_choice)
        self.config.mic_device = mic_choice if self.mic_devices else ""
        self.config.system_device = system_choice if system_choice != "None" else ""
        self._restart_level_monitor()

    def _on_mic_selected(self, value: str):
        self.config.mic_device = value if value != "No microphones found" else ""
        self._restart_level_monitor()

    def _on_system_selected(self, value: str):
        self.config.system_device = value if value != "None" else ""
        self._restart_level_monitor()

    def _on_model_selected(self, value: str):
        self.config.transcription_model = value

    def _selected_mic_device(self) -> Optional[AudioDevice]:
        return find_device_by_label(self.mic_devices, self.mic_menu.get())

    def _selected_system_device(self) -> Optional[AudioDevice]:
        selected = self.system_menu.get()
        if selected == "None":
            return None
        return find_device_by_label(self.system_devices, selected)

    def _toggle_live_recording(self):
        if self.is_recording:
            self._stop_live_recording()
        else:
            self._start_live_recording()

    def _stop_level_monitor(self):
        if self.live_monitor is not None:
            self.live_monitor.stop()
            self.live_monitor = None

    def _restart_level_monitor(self):
        if self.is_recording or not hasattr(self, "live_mode_frame"):
            return
        if self.current_mode != "Live Recording":
            return

        self._stop_level_monitor()
        mic_device = self._selected_mic_device()
        system_device = self._selected_system_device()
        if mic_device is None and system_device is None:
            self._set_live_levels(0, 0)
            return

        try:
            self.live_monitor = LiveAudioLevelMonitor(
                mic_device=mic_device,
                system_device=system_device,
                level_callback=self._set_live_levels,
            )
            self.live_monitor.start()
            self.live_status_label.configure(
                text="Meters are live. Speak or play Teams audio to verify the selected devices."
            )
        except LiveRecorderError as e:
            self.live_monitor = None
            self.live_status_label.configure(text=f"Meter preview unavailable: {e}")

    def _set_live_controls_state(self, state: str):
        self.mic_menu.configure(state=state)
        self.system_menu.configure(state=state)
        self.model_menu.configure(state=state)

    def _update_live_status(self, message: str):
        self.after(0, lambda: self.live_status_label.configure(text=message))

    def _set_live_levels(self, mic_level: float, system_level: float):
        self.after(0, lambda: (
            self.mic_level_bar.set(mic_level),
            self.system_level_bar.set(system_level)
        ))

    def _append_live_transcript(self, text: str):
        if not text:
            return

        def update():
            self.live_transcript += text
            self.transcript_box.configure(state="normal")
            self.transcript_box.insert("end", text)
            self.transcript_box.see("end")
            self.transcript_box.configure(state="disabled")

        self.after(0, update)

    def _copy_live_transcript_to_clipboard(self):
        """Copy the current live transcript text to the system clipboard."""
        text = self.live_transcript.strip()
        if not text:
            text = self.transcript_box.get("1.0", "end").strip()
        if not text or text == "Transcript will appear here while recording.":
            self.live_status_label.configure(text="No transcript to copy yet.")
            return

        self.clipboard_clear()
        self.clipboard_append(text)
        self.update_idletasks()
        self.live_status_label.configure(text="Transcript copied to clipboard.")

    def _reset_live_transcript(self):
        self.live_transcript = ""
        self.transcript_box.configure(state="normal")
        self.transcript_box.delete("1.0", "end")
        self.transcript_box.configure(state="disabled")

    def _replace_live_transcript(self, text: str):
        def update():
            self.live_transcript = text
            self.transcript_box.configure(state="normal")
            self.transcript_box.delete("1.0", "end")
            self.transcript_box.insert("1.0", text)
            self.transcript_box.see("end")
            self.transcript_box.configure(state="disabled")

        self.after(0, update)

    def _update_recording_timer(self):
        if not self.is_recording or self.live_recorder is None:
            return

        elapsed = self.live_recorder.elapsed_seconds
        minutes, seconds = divmod(elapsed, 60)
        self.live_status_label.configure(
            text=(
                f"Recording {minutes:02d}:{seconds:02d} - transcript updates about every "
                f"{LIVE_TRANSCRIPTION_SEGMENT_SECONDS} seconds."
            )
        )
        self.after(1000, self._update_recording_timer)

    def _start_live_recording(self):
        """Start live recording and rolling transcription."""
        api_key = self.config.resolved_api_key()
        if not api_key:
            messagebox.showerror(
                "OpenAI API Key Required",
                f"Please set the {self.config.api_key_env_var} environment variable before recording."
            )
            self._open_settings()
            return

        mic_device = self._selected_mic_device()
        system_device = self._selected_system_device()
        if mic_device is None and system_device is None:
            messagebox.showerror(
                "Audio Device Required",
                "Select at least one microphone or system audio device."
            )
            return

        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.live_audio_path = output_dir / f"meeting_{timestamp}.wav"
        self.live_transcript_path = output_dir / f"meeting_{timestamp}_transcription.txt"
        logger.info(
            "Starting live recording (mic=%s, system=%s, model=%s, output_audio=%s)",
            self.mic_menu.get(),
            self.system_menu.get(),
            self.model_menu.get(),
            self.live_audio_path,
        )

        self._stop_level_monitor()
        self._reset_live_transcript()
        self._set_live_controls_state("disabled")
        self.record_btn.configure(
            text="Stop Recording",
            fg_color=DANGER_BUTTON_FG_COLOR,
            hover_color=DANGER_BUTTON_HOVER_COLOR,
        )
        self._update_status("Recording live audio...")

        self.live_transcriber = RollingStreamingTranscriber(
            api_key=api_key,
            model=self.model_menu.get(),
            on_delta=self._append_live_transcript,
            on_status=self._update_live_status,
            on_error=lambda message: self._update_live_status(f"Transcription error: {message}"),
        )
        self.live_transcriber.start()

        self.live_recorder = LiveAudioRecorder(
            mic_device=mic_device,
            system_device=system_device,
            output_path=self.live_audio_path,
            level_callback=self._set_live_levels,
            segment_callback=self._queue_live_audio_segment,
            segment_seconds=LIVE_TRANSCRIPTION_SEGMENT_SECONDS,
        )

        try:
            self.live_recorder.start()
        except LiveRecorderError as e:
            logger.exception("Failed to start live recording.")
            self.live_transcriber.stop(wait=False)
            self.live_transcriber = None
            self.live_recorder = None
            self._set_live_controls_state("normal")
            self.record_btn.configure(
                text="Start Recording",
                fg_color=PRIMARY_BUTTON_FG_COLOR,
                hover_color=PRIMARY_BUTTON_HOVER_COLOR,
            )
            self._restart_level_monitor()
            messagebox.showerror("Live Recording", str(e))
            return

        self.is_recording = True
        self._update_recording_timer()

    def _queue_live_audio_segment(self, samples, sample_rate: int, final: bool = False):
        """Send the already-mixed recorder segment to the transcription worker."""
        if self.live_transcriber is None:
            return
        self.live_transcriber.add_audio_segment(samples, sample_rate, final)
        if final:
            self._update_live_status("Queued final audio for transcription...")
        else:
            self._update_live_status("Queued recent audio for transcription...")

    def _stop_live_recording(self):
        """Stop live recording without blocking the UI thread."""
        if not self.is_recording:
            return

        self.is_recording = False
        self.record_btn.configure(text="Stopping...", state="disabled")
        self._update_live_status("Stopping recording and finalizing transcript...")
        threading.Thread(target=self._stop_live_recording_worker, daemon=True).start()

    def _stop_live_recording_worker(self):
        audio_path = self.live_audio_path
        transcript_path = self.live_transcript_path

        try:
            if self.live_recorder is not None:
                audio_path = self.live_recorder.stop()

            final_text = ""
            if self.live_transcriber is not None:
                final_text = self.live_transcriber.stop(wait=True)

            if self.live_transcript.strip():
                final_text = self.live_transcript
            elif not final_text:
                final_text = self.live_transcript

            if transcript_path is not None:
                saved_transcript = save_transcription(final_text, str(transcript_path))
            else:
                saved_transcript = ""
            logger.info(
                "Live recording completed (audio=%s, transcript=%s)",
                audio_path,
                saved_transcript,
            )

            self._replace_live_transcript(final_text)
            self.after(0, lambda: self._finish_live_recording_ui(audio_path, saved_transcript))
        except Exception as e:
            logger.exception("Live recording failed while finalizing.")
            message = str(e)
            self.after(0, lambda msg=message: self._fail_live_recording_ui(msg))

    def _finish_live_recording_ui(self, audio_path: Optional[Path], transcript_path: str):
        self.live_recorder = None
        self.live_transcriber = None
        self._set_live_controls_state("normal")
        self.record_btn.configure(
            text="Start Recording",
            state="normal",
            fg_color=PRIMARY_BUTTON_FG_COLOR,
            hover_color=PRIMARY_BUTTON_HOVER_COLOR,
        )
        self.mic_level_bar.set(0)
        self.system_level_bar.set(0)
        self._update_status("Live recording complete.")
        self.live_status_label.configure(
            text=f"Saved audio: {Path(audio_path).name if audio_path else 'n/a'} | "
                 f"Transcript: {Path(transcript_path).name if transcript_path else 'n/a'}"
        )
        messagebox.showinfo(
            "Live Recording Complete",
            f"Audio saved to:\n{audio_path}\n\nTranscript saved to:\n{transcript_path}"
        )
        self._restart_level_monitor()

    def _fail_live_recording_ui(self, message: str):
        self.live_recorder = None
        self.live_transcriber = None
        self._set_live_controls_state("normal")
        self.record_btn.configure(
            text="Start Recording",
            state="normal",
            fg_color=PRIMARY_BUTTON_FG_COLOR,
            hover_color=PRIMARY_BUTTON_HOVER_COLOR,
        )
        self._update_status("Live recording failed.")
        self.live_status_label.configure(text=f"Live recording failed: {message}")
        messagebox.showerror("Live Recording", message)
        self._restart_level_monitor()
    
    def _setup_drag_drop(self):
        """Register the drop zone (and descendants) for OS-level file drops."""
        if not getattr(self, "dnd_available", False):
            return
        for widget in self._walk(self.drop_zone):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_files_dropped)
            widget.dnd_bind("<<DragEnter>>", self._on_drag_enter)
            widget.dnd_bind("<<DragLeave>>", self._on_drag_leave)

    @staticmethod
    def _walk(widget):
        yield widget
        for child in widget.winfo_children():
            yield from TranscriberApp._walk(child)

    def _on_files_dropped(self, event):
        self._reset_drop_zone_style()
        # event.data is a Tcl list; splitlist handles spaces and {braced} paths.
        for path in self.tk.splitlist(event.data):
            self._add_file(path)
        return "break"

    def _on_drag_enter(self, _event):
        if self._drag_leave_after is not None:
            self.after_cancel(self._drag_leave_after)
            self._drag_leave_after = None
        self.drop_zone.configure(border_color=PRIMARY_BUTTON_FG_COLOR)

    def _on_drag_leave(self, _event):
        if self._drag_leave_after is not None:
            self.after_cancel(self._drag_leave_after)
        self._drag_leave_after = self.after(60, self._reset_drop_zone_style)

    def _reset_drop_zone_style(self):
        self._drag_leave_after = None
        self.drop_zone.configure(border_color=BORDER_COLOR)
    
    def _browse_files(self):
        """Open file browser to select audio files."""
        filetypes = [
            ("Audio files", " ".join(f"*{ext}" for ext in SUPPORTED_EXTENSIONS)),
            ("All files", "*.*")
        ]
        
        files = filedialog.askopenfilenames(
            title="Select Audio Files",
            filetypes=filetypes
        )
        
        for file_path in files:
            self._add_file(file_path)
    
    def _add_file(self, file_path: str):
        """Add a file to the queue."""
        # Check if already in queue
        for item in self.file_items:
            if item.file_path == file_path:
                return
        
        # Check file extension
        if not file_path.lower().endswith(SUPPORTED_EXTENSIONS):
            messagebox.showwarning(
                "Unsupported Format",
                f"File format not supported:\n{Path(file_path).name}"
            )
            return
        
        # Hide empty message
        self.empty_label.pack_forget()
        
        # Create file item
        file_item = FileItem(
            self.queue_frame, 
            file_path, 
            on_remove=self._remove_file
        )
        file_item.pack(fill="x", pady=5)
        self.file_items.append(file_item)
        
        self._update_buttons()
    
    def _remove_file(self, file_item: FileItem):
        """Remove a file from the queue."""
        file_item.destroy()
        self.file_items.remove(file_item)
        
        if not self.file_items:
            self.empty_label.pack(pady=40)
        
        self._update_buttons()
    
    def _clear_queue(self):
        """Clear all files from the queue."""
        if self.is_processing:
            return
            
        for item in self.file_items[:]:
            item.destroy()
        self.file_items.clear()
        
        self.empty_label.pack(pady=40)
        self._update_buttons()
    
    def _update_buttons(self):
        """Update button states based on queue."""
        has_files = len(self.file_items) > 0
        
        self.clear_btn.configure(
            state="normal" if has_files and not self.is_processing else "disabled"
        )
        self.transcribe_btn.configure(
            state="normal" if has_files and not self.is_processing else "disabled"
        )
    
    def _prompt_api_key(self):
        """Prompt user to configure the OpenAI API key environment variable."""
        dialog = SettingsDialog(self, self.config)
        self.wait_window(dialog)
        if dialog.result:
            self._apply_theme_from_config()
    
    def _open_settings(self):
        """Open settings dialog."""
        dialog = SettingsDialog(self, self.config)
        self.wait_window(dialog)
        if dialog.result:
            self._apply_theme_from_config()

    def _apply_theme_from_config(self):
        theme_map = {"System": "system", "White": "light", "Dark": "dark"}
        ctk.set_appearance_mode(theme_map.get(self.config.theme, "system"))

    def _open_output_directory(self):
        try:
            open_directory(Path(self.config.output_dir))
        except Exception as exc:
            messagebox.showerror("Output Directory", f"Could not open output directory:\n{exc}")
    
    def _start_transcription(self):
        """Start transcribing all files in the queue."""
        api_key = self.config.resolved_api_key()
        if not api_key:
            messagebox.showerror(
                "OpenAI API Key Required",
                f"Please set the {self.config.api_key_env_var} environment variable before transcribing."
            )
            self._open_settings()
            return
        
        if not self.file_items:
            return
        
        self.is_processing = True
        self._update_buttons()
        
        # Create output directory
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize transcriber
        self.transcriber = AudioTranscriber(api_key)
        logger.info("Starting batch transcription for %s queued file(s).", len(self.file_items))
        
        # Start processing in background thread
        thread = threading.Thread(target=self._process_queue, daemon=True)
        thread.start()
    
    def _process_queue(self):
        """Process all files in the queue (runs in background thread)."""
        output_dir = Path(self.config.output_dir)
        
        for file_item in self.file_items:
            if file_item.status == "complete":
                continue
            
            try:
                logger.info("Transcribing file: %s", file_item.file_path)
                # Update UI
                self._update_file_status(file_item, "processing", "Processing...")
                self._update_status(f"Transcribing: {Path(file_item.file_path).name}")
                
                # Define progress callback
                def progress_callback(message: str, progress: float):
                    self.after(0, lambda m=message, p=progress: (
                        file_item.set_status("processing", m),
                        file_item.set_progress(p)
                    ))
                
                # Transcribe
                result = self.transcriber.transcribe(
                    file_item.file_path,
                    progress_callback=progress_callback
                )
                
                # Save result
                input_path = Path(file_item.file_path)
                output_path = output_dir / f"{input_path.stem}_transcription.txt"
                saved_path = save_transcription(result, str(output_path))
                
                # Update UI
                self._update_file_status(file_item, "complete", f"Saved: {Path(saved_path).name}")
                file_item.set_progress(1.0)
                logger.info("Completed file: %s", saved_path)
                
            except TranscriptionError as e:
                logger.exception("Transcription error for file: %s", file_item.file_path)
                self._update_file_status(file_item, "error", str(e))
            except Exception as e:
                logger.exception("Unexpected error for file: %s", file_item.file_path)
                self._update_file_status(file_item, "error", f"Error: {str(e)}")
        
        # All done
        self.is_processing = False
        self.after(0, self._update_buttons)
        self._update_status("Transcription complete!")
        logger.info("Batch transcription finished.")
        
        # Show completion message
        completed = sum(1 for item in self.file_items if item.status == "complete")
        failed = sum(1 for item in self.file_items if item.status == "error")
        
        self.after(0, lambda: messagebox.showinfo(
            "Transcription Complete",
            f"Processed {len(self.file_items)} files:\n"
            f"  ✓ {completed} completed\n"
            f"  ✗ {failed} failed\n\n"
            f"Output saved to:\n{self.config.output_dir}"
        ))
    
    def _update_file_status(self, file_item: FileItem, status: str, message: str):
        """Update file status from background thread."""
        self.after(0, lambda: file_item.set_status(status, message))
    
    def _update_status(self, message: str):
        """Update status bar from background thread."""
        self.after(0, lambda: self.status_label.configure(text=message))


def main():
    """Application entry point."""
    setup_logging()
    logger.info("Launching %s", APP_NAME)
    app = TranscriberApp()
    app.mainloop()


if __name__ == "__main__":
    main()
