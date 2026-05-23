"""Controller for file queue transcription orchestration."""

from __future__ import annotations

import threading
from pathlib import Path
from tkinter import messagebox

from ..transcriber import AudioTranscriber, TranscriptionError, save_transcription


class FileQueueController:
    """Coordinate batch file transcription without owning UI widgets."""

    def __init__(self, app, logger):
        self.app = app
        self.logger = logger

    def start_transcription(self):
        """Start transcribing all files in the queue."""
        api_key = self.app.config.resolved_api_key()
        if not api_key:
            messagebox.showerror(
                "OpenAI API Key Required",
                f"Please set the {self.app.config.api_key_env_var} environment variable before transcribing.",
            )
            self.app._open_settings()
            return

        if not self.app.file_items:
            return

        self.app.is_processing = True
        self.app._update_buttons()

        output_dir = Path(self.app.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        self.app.transcriber = AudioTranscriber(api_key)
        self.logger.info("Starting batch transcription for %s queued file(s).", len(self.app.file_items))
        threading.Thread(target=self.process_queue, daemon=True).start()

    def process_queue(self):
        """Process all files in the queue (runs in background thread)."""
        output_dir = Path(self.app.config.output_dir)

        for file_item in self.app.file_items:
            if file_item.status == "complete":
                continue

            try:
                self.logger.info("Transcribing file: %s", file_item.file_path)
                self.app._update_file_status(file_item, "processing", "Processing...")
                self.app._update_status(f"Transcribing: {Path(file_item.file_path).name}")

                def progress_callback(message: str, progress: float):
                    self.app.after(
                        0,
                        lambda m=message, p=progress: (
                            file_item.set_status("processing", m),
                            file_item.set_progress(p),
                        ),
                    )

                result = self.app.transcriber.transcribe(
                    file_item.file_path,
                    progress_callback=progress_callback,
                )

                input_path = Path(file_item.file_path)
                output_path = output_dir / f"{input_path.stem}_transcription.txt"
                saved_path = save_transcription(result, str(output_path))

                self.app._update_file_status(file_item, "complete", f"Saved: {Path(saved_path).name}")
                file_item.set_progress(1.0)
                self.logger.info("Completed file: %s", saved_path)

            except TranscriptionError as exc:
                self.logger.exception("Transcription error for file: %s", file_item.file_path)
                self.app._update_file_status(file_item, "error", str(exc))
            except Exception as exc:
                self.logger.exception("Unexpected error for file: %s", file_item.file_path)
                self.app._update_file_status(file_item, "error", f"Error: {str(exc)}")

        self.app.is_processing = False
        self.app.after(0, self.app._update_buttons)
        self.app._update_status("Transcription complete!")
        self.logger.info("Batch transcription finished.")

        completed = sum(1 for item in self.app.file_items if item.status == "complete")
        failed = sum(1 for item in self.app.file_items if item.status == "error")
        self.app.after(
            0,
            lambda: messagebox.showinfo(
                "Transcription Complete",
                f"Processed {len(self.app.file_items)} files:\n"
                f"  ✓ {completed} completed\n"
                f"  ✗ {failed} failed\n\n"
                f"Output saved to:\n{self.app.config.output_dir}",
            ),
        )

