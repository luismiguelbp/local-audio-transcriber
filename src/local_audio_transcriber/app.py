"""
Local Audio Transcriber

A desktop GUI application for transcribing audio files using OpenAI's Whisper API.
Handles long meeting recordings by automatically chunking files.
"""

import logging
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Optional

import customtkinter as ctk
from dotenv import load_dotenv
from tkinterdnd2 import DND_FILES, TkinterDnD

from .live_recorder import (
    AudioDevice,
    LiveAudioLevelMonitor,
    LiveRecorderError,
    device_labels,
    find_device_by_label,
    list_microphones,
    list_system_outputs,
)
from .streaming_transcriber import ACCURATE_MODEL, DEFAULT_MODEL
from .controllers.file_queue_controller import FileQueueController
from .controllers.live_recording_controller import LiveRecordingController
from .config import (
    ConfigManager,
    LIVE_RECORDING_MODES,
    LIVE_TRANSCRIPT_MODE,
    RECORD_AND_TRANSCRIBE_MODE,
)
from .logging_setup import setup_logging
from .ui.dialogs import SettingsDialog, open_directory
from .ui.theme import (
    ACTION_BUTTON_TEXT_COLOR,
    APP_BG_COLOR,
    BORDER_COLOR,
    CONTROL_HEIGHT,
    DANGER_BUTTON_FG_COLOR,
    DANGER_BUTTON_HOVER_COLOR,
    HELPER_TEXT_SIZE,
    MUTED_TEXT_COLOR,
    PRIMARY_BUTTON_FG_COLOR,
    PRIMARY_BUTTON_HOVER_COLOR,
    PRIMARY_TEXT_COLOR,
    SECONDARY_BUTTON_FG_COLOR,
    SECONDARY_BUTTON_HOVER_COLOR,
    SECONDARY_BUTTON_TEXT_COLOR,
    SUCCESS_BUTTON_FG_COLOR,
    SUCCESS_BUTTON_HOVER_COLOR,
    secondary_button_style,
)
from .ui.views import FileUploadView, LiveRecordingView
from .ui.widgets import FileItem


# Load environment variables
load_dotenv()

# App configuration
APP_NAME = "Local Audio Transcriber"
SUPPORTED_EXTENSIONS = ('.mp3', '.wav', '.m4a', '.mp4', '.mkv', '.webm', '.ogg', '.flac')
logger = logging.getLogger(__name__)

LIVE_TRANSCRIPTION_SEGMENT_SECONDS = 10


def recording_mode_help_text(mode: str) -> str:
    if mode == RECORD_AND_TRANSCRIBE_MODE:
        return "Best for accuracy: transcribes once after you stop recording."
    return "Best for immediacy: shows transcript updates while recording."


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
        self.live_cancel_requested = False
        self.current_mode = "File Upload"
        self.live_transcript = ""
        self.live_audio_path: Optional[Path] = None
        self.live_transcript_path: Optional[Path] = None
        self._drag_leave_after: Optional[str] = None
        self._closing_in_progress = False
        self._close_finished = False
        self.file_queue_controller = FileQueueController(self, logger)
        self.live_recording_controller = LiveRecordingController(
            self,
            logger,
            live_transcript_mode=LIVE_TRANSCRIPT_MODE,
            record_and_transcribe_mode=RECORD_AND_TRANSCRIBE_MODE,
            segment_seconds=LIVE_TRANSCRIPTION_SEGMENT_SECONDS,
        )
        
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
        if self._closing_in_progress:
            return
        self._closing_in_progress = True
        self._close_finished = False
        logger.info("Closing application.")
        self.after(2500, self._force_destroy_on_close_timeout)
        threading.Thread(target=self._close_worker, daemon=True).start()

    def _close_worker(self):
        try:
            self.live_cancel_requested = True
            self._stop_level_monitor(force=True)
            if self.is_recording:
                self.is_recording = False
                if self.live_recorder is not None:
                    self.live_recorder.stop(force=True)
                if self.live_transcriber is not None:
                    self.live_transcriber.stop(wait=False)
        except Exception:
            logger.exception("Error while closing audio resources.")
        finally:
            self.after(0, self._finish_close)

    def _finish_close(self):
        if self._close_finished:
            return
        self._close_finished = True
        self.destroy()

    def _force_destroy_on_close_timeout(self):
        if self._close_finished:
            return
        logger.warning("Close timeout reached. Forcing application shutdown.")
        self._finish_close()
    
    def _create_widgets(self):
        """Create all UI widgets."""
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(18, 10))
        
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
            **secondary_button_style(),
            command=self._open_settings
        ).pack(side="right")
        ctk.CTkButton(
            header_frame,
            text="Output",
            width=92,
            **secondary_button_style(),
            command=self._open_output_directory,
        ).pack(side="right", padx=(0, 10))

        self.mode_selector = ctk.CTkSegmentedButton(
            self,
            values=["File Upload", "Live Recording"],
            command=self._switch_mode,
            height=CONTROL_HEIGHT + 2,
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
            font=ctk.CTkFont(size=HELPER_TEXT_SIZE),
            text_color=MUTED_TEXT_COLOR,
        )
        self.status_label.pack(pady=(0, 12))

    def _create_file_upload_widgets(self):
        """Create the existing file upload workflow."""
        self.file_upload_view = FileUploadView(
            self.file_mode_frame,
            supported_extensions=SUPPORTED_EXTENSIONS,
            on_browse_files=self._browse_files,
            on_clear_queue=self._clear_queue,
            on_start_transcription=self._start_transcription,
        )
        self.file_upload_view.pack(fill="both", expand=True)

        self.drop_zone = self.file_upload_view.drop_zone
        self.queue_frame = self.file_upload_view.queue_frame
        self.empty_state_frame = self.file_upload_view.empty_state_frame
        self.clear_btn = self.file_upload_view.clear_btn
        self.transcribe_btn = self.file_upload_view.transcribe_btn

    def _create_live_recording_widgets(self):
        """Create the live recording workflow."""
        model_choice = self.config.transcription_model
        if model_choice not in (DEFAULT_MODEL, ACCURATE_MODEL):
            model_choice = DEFAULT_MODEL

        mode_choice = self.config.live_recording_mode
        self.live_recording_view = LiveRecordingView(
            self.live_mode_frame,
            model_values=[DEFAULT_MODEL, ACCURATE_MODEL],
            mode_values=list(LIVE_RECORDING_MODES),
            mode_help_text=recording_mode_help_text(mode_choice),
            on_refresh_devices=self._refresh_audio_devices,
            on_model_selected=self._on_model_selected,
            on_mode_selected=self._on_live_recording_mode_selected,
            on_toggle_recording=self._toggle_live_recording,
            on_cancel_recording=self._cancel_live_recording,
            on_copy_transcript=self._copy_live_transcript_to_clipboard,
        )
        self.live_recording_view.pack(fill="both", expand=True)

        self.mic_menu = self.live_recording_view.mic_menu
        self.system_menu = self.live_recording_view.system_menu
        self.model_menu = self.live_recording_view.model_menu
        self.live_recording_mode_menu = self.live_recording_view.live_recording_mode_menu
        self.mode_help_label = self.live_recording_view.mode_help_label
        self.mic_level_bar = self.live_recording_view.mic_level_bar
        self.system_level_bar = self.live_recording_view.system_level_bar
        self.record_btn = self.live_recording_view.record_btn
        self.cancel_record_btn = self.live_recording_view.cancel_record_btn
        self.live_status_label = self.live_recording_view.live_status_label
        self.transcript_box = self.live_recording_view.transcript_box

        self.model_menu.set(model_choice)
        self.config.transcription_model = model_choice
        self.live_recording_mode_menu.set(mode_choice)
        self.config.live_recording_mode = mode_choice
        self._set_record_action_buttons_idle()
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
            # Stop preview meters off the UI thread when leaving Live mode to avoid tab-switch freezes.
            self._stop_level_monitor(background=True)
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

    def _on_live_recording_mode_selected(self, value: str):
        self.config.live_recording_mode = value
        self.mode_help_label.configure(text=recording_mode_help_text(value))

    def _selected_live_recording_mode(self) -> str:
        selected = self.live_recording_mode_menu.get()
        if selected not in LIVE_RECORDING_MODES:
            return LIVE_TRANSCRIPT_MODE
        return selected

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

    def _stop_level_monitor(self, force: bool = False, background: bool = False):
        monitor = self.live_monitor
        self.live_monitor = None
        if monitor is None:
            return
        if background:
            threading.Thread(target=monitor.stop, kwargs={"force": force}, daemon=True).start()
            return
        monitor.stop(force=force)

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
        self.live_recording_mode_menu.configure(state=state)

    def _update_live_status(self, message: str):
        self.after(0, lambda: self.live_status_label.configure(text=message))

    def _set_record_action_buttons_idle(self):
        self.record_btn.configure(
            text="Start Recording",
            state="normal",
            fg_color=PRIMARY_BUTTON_FG_COLOR,
            hover_color=PRIMARY_BUTTON_HOVER_COLOR,
            text_color=ACTION_BUTTON_TEXT_COLOR,
        )
        self.cancel_record_btn.configure(state="disabled")
        if self.cancel_record_btn.winfo_manager():
            self.cancel_record_btn.pack_forget()

    def _set_record_action_buttons_recording(self):
        self.record_btn.configure(
            text="Stop Recording",
            state="normal",
            fg_color=SUCCESS_BUTTON_FG_COLOR,
            hover_color=SUCCESS_BUTTON_HOVER_COLOR,
            text_color=ACTION_BUTTON_TEXT_COLOR,
        )
        self.cancel_record_btn.configure(
            state="normal",
            fg_color=DANGER_BUTTON_FG_COLOR,
            hover_color=DANGER_BUTTON_HOVER_COLOR,
            text_color=ACTION_BUTTON_TEXT_COLOR,
        )
        if not self.cancel_record_btn.winfo_manager():
            self.cancel_record_btn.pack(side="left", padx=(10, 0), before=self.live_status_label)

    def _set_record_action_buttons_busy(self, record_text: str):
        self.record_btn.configure(text=record_text, state="disabled")
        self.cancel_record_btn.configure(state="disabled")

    def _cleanup_live_recording_files(
        self,
        audio_path: Optional[Path],
        transcript_path: Optional[Path] = None,
    ) -> None:
        for path in (audio_path, transcript_path):
            if path is None:
                continue
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass

    def _set_live_levels(self, mic_level: float, system_level: float):
        self.after(0, lambda: (
            self.mic_level_bar.set(mic_level),
            self.system_level_bar.set(system_level)
        ))

    def _append_live_transcript(self, text: str):
        if not text or self.live_cancel_requested:
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
        self.live_recording_controller.update_recording_timer()

    def _start_live_recording(self):
        self.live_recording_controller.start()

    def _queue_live_audio_segment(self, samples, sample_rate: int, final: bool = False):
        self.live_recording_controller.queue_live_audio_segment(samples, sample_rate, final)

    def _stop_live_recording(self):
        self.live_recording_controller.stop()

    def _cancel_live_recording(self):
        self.live_recording_controller.cancel()

    def _cancel_live_recording_worker(self):
        self.live_recording_controller.cancel_worker()

    def _stop_live_recording_worker(self):
        self.live_recording_controller.stop_worker()

    def _finish_live_recording_ui(self, audio_path: Optional[Path], transcript_path: str):
        self.live_recorder = None
        self.live_transcriber = None
        self.live_cancel_requested = False
        self.live_audio_path = None
        self.live_transcript_path = None
        self._set_live_controls_state("normal")
        self._set_record_action_buttons_idle()
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

    def _finish_live_recording_cancel_ui(self):
        self.live_recorder = None
        self.live_transcriber = None
        self.live_audio_path = None
        self.live_transcript_path = None
        self.live_cancel_requested = False
        self._set_live_controls_state("normal")
        self._set_record_action_buttons_idle()
        self._reset_live_transcript()
        self.mic_level_bar.set(0)
        self.system_level_bar.set(0)
        self._update_status("Live recording canceled.")
        self.live_status_label.configure(text="Recording canceled. Discarded audio and transcript.")
        self._restart_level_monitor()

    def _fail_live_recording_ui(self, message: str):
        self.live_recorder = None
        self.live_transcriber = None
        self.live_cancel_requested = False
        self._set_live_controls_state("normal")
        self._set_record_action_buttons_idle()
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
        
        # Hide empty state
        self._hide_empty_queue_state()
        
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
            self._show_empty_queue_state()
        
        self._update_buttons()
    
    def _clear_queue(self):
        """Clear all files from the queue."""
        if self.is_processing:
            return
            
        for item in self.file_items[:]:
            item.destroy()
        self.file_items.clear()
        
        self._show_empty_queue_state()
        self._update_buttons()

    def _show_empty_queue_state(self):
        self.file_upload_view.show_empty_state()

    def _hide_empty_queue_state(self):
        self.file_upload_view.hide_empty_state()
    
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
        self.file_queue_controller.start_transcription()
    
    def _process_queue(self):
        self.file_queue_controller.process_queue()
    
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
