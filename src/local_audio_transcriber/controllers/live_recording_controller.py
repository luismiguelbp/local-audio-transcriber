"""Controller for live recording orchestration."""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

from ..live_recorder import LiveAudioRecorder, LiveRecorderError
from ..streaming_transcriber import RollingStreamingTranscriber
from ..transcriber import AudioTranscriber, TranscriptionError, save_transcription


class LiveRecordingController:
    """Coordinate live recording lifecycle and background work."""

    def __init__(
        self,
        app,
        logger,
        live_transcript_mode: str,
        record_and_transcribe_mode: str,
        segment_seconds: int,
    ):
        self.app = app
        self.logger = logger
        self.live_transcript_mode = live_transcript_mode
        self.record_and_transcribe_mode = record_and_transcribe_mode
        self.segment_seconds = segment_seconds

    def update_recording_timer(self):
        if not self.app.is_recording or self.app.live_recorder is None:
            return

        elapsed = self.app.live_recorder.elapsed_seconds
        minutes, seconds = divmod(elapsed, 60)
        if self.app._selected_live_recording_mode() == self.record_and_transcribe_mode:
            self.app.live_status_label.configure(
                text=f"Recording {minutes:02d}:{seconds:02d} - transcript will be generated after stop."
            )
        else:
            self.app.live_status_label.configure(
                text=(
                    f"Recording {minutes:02d}:{seconds:02d} - transcript updates about every "
                    f"{self.segment_seconds} seconds."
                )
            )
        self.app.after(1000, self.app._update_recording_timer)

    def start(self):
        """Start live recording and rolling transcription."""
        api_key = self.app.config.resolved_api_key()
        if not api_key:
            messagebox.showerror(
                "OpenAI API Key Required",
                f"Please set the {self.app.config.api_key_env_var} environment variable before recording.",
            )
            self.app._open_settings()
            return

        mic_device = self.app._selected_mic_device()
        system_device = self.app._selected_system_device()
        if mic_device is None and system_device is None:
            messagebox.showerror(
                "Audio Device Required",
                "Select at least one microphone or system audio device.",
            )
            return

        output_dir = Path(self.app.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.app.live_audio_path = output_dir / f"meeting_{timestamp}.wav"
        self.app.live_transcript_path = output_dir / f"meeting_{timestamp}_transcription.txt"
        recording_mode = self.app._selected_live_recording_mode()
        self.logger.info(
            "Starting live recording (mode=%s, mic=%s, system=%s, model=%s, output_audio=%s)",
            recording_mode,
            self.app.mic_menu.get(),
            self.app.system_menu.get(),
            self.app.model_menu.get(),
            self.app.live_audio_path,
        )

        self.app._stop_level_monitor()
        self.app._reset_live_transcript()
        self.app.live_cancel_requested = False
        self.app._set_live_controls_state("disabled")
        self.app._set_record_action_buttons_recording()
        if recording_mode == self.record_and_transcribe_mode:
            self.app.live_transcriber = None
            self.app._update_status("Recording audio for later transcription...")
            self.app._update_live_status("Recording audio. Transcript will be generated after stop.")
        else:
            self.app._update_status("Recording live audio...")
            self.app.live_transcriber = RollingStreamingTranscriber(
                api_key=api_key,
                model=self.app.model_menu.get(),
                on_delta=self.app._append_live_transcript,
                on_status=self.app._update_live_status,
                on_error=lambda message: self.app._update_live_status(f"Transcription error: {message}"),
            )
            self.app.live_transcriber.start()

        segment_callback = self.app._queue_live_audio_segment if recording_mode == self.live_transcript_mode else None
        self.app.live_recorder = LiveAudioRecorder(
            mic_device=mic_device,
            system_device=system_device,
            output_path=self.app.live_audio_path,
            level_callback=self.app._set_live_levels,
            segment_callback=segment_callback,
            segment_seconds=self.segment_seconds,
        )

        try:
            self.app.live_recorder.start()
        except LiveRecorderError as exc:
            self.logger.exception("Failed to start live recording.")
            if self.app.live_transcriber is not None:
                self.app.live_transcriber.stop(wait=False)
            self.app.live_transcriber = None
            self.app.live_recorder = None
            self.app._set_live_controls_state("normal")
            self.app._set_record_action_buttons_idle()
            self.app._restart_level_monitor()
            messagebox.showerror("Live Recording", str(exc))
            return

        self.app.is_recording = True
        self.update_recording_timer()

    def queue_live_audio_segment(self, samples, sample_rate: int, final: bool = False):
        if self.app.live_transcriber is None or self.app.live_cancel_requested:
            return
        self.app.live_transcriber.add_audio_segment(samples, sample_rate, final)
        if final:
            self.app._update_live_status("Queued final audio for transcription...")
        else:
            self.app._update_live_status("Queued recent audio for transcription...")

    def stop(self):
        """Stop live recording without blocking the UI thread."""
        if not self.app.is_recording:
            return
        self.app.is_recording = False
        self.app.live_cancel_requested = False
        self.app._set_record_action_buttons_busy("Stopping...")
        if self.app._selected_live_recording_mode() == self.record_and_transcribe_mode:
            self.app._update_live_status("Stopping recording...")
        else:
            self.app._update_live_status("Stopping recording and finalizing transcript...")
        threading.Thread(target=self.stop_worker, daemon=True).start()

    def cancel(self):
        """Cancel active recording and discard generated outputs."""
        if not self.app.is_recording:
            return
        self.app.is_recording = False
        self.app.live_cancel_requested = True
        self.app._set_record_action_buttons_busy("Canceling...")
        self.app._update_status("Canceling live recording...")
        self.app._update_live_status("Canceling recording. Discarding audio and transcript...")
        threading.Thread(target=self.cancel_worker, daemon=True).start()

    def cancel_worker(self):
        audio_path = self.app.live_audio_path
        transcript_path = self.app.live_transcript_path
        try:
            if self.app.live_recorder is not None:
                audio_path = self.app.live_recorder.stop(force=True)
            if self.app.live_transcriber is not None:
                self.app.live_transcriber.stop(wait=False)
            self.app._cleanup_live_recording_files(audio_path, transcript_path)
            self.app.after(0, self.app._finish_live_recording_cancel_ui)
        except Exception as exc:
            self.logger.exception("Live recording cancel failed.")
            message = str(exc)
            self.app.after(0, lambda msg=message: self.app._fail_live_recording_ui(msg))

    def stop_worker(self):
        audio_path = self.app.live_audio_path
        transcript_path = self.app.live_transcript_path
        recording_mode = self.app._selected_live_recording_mode()

        try:
            if self.app.live_recorder is not None:
                audio_path = self.app.live_recorder.stop()

            final_text = ""
            if recording_mode == self.live_transcript_mode:
                if self.app.live_transcriber is not None:
                    final_text = self.app.live_transcriber.stop(wait=True)
                if self.app.live_transcript.strip():
                    final_text = self.app.live_transcript
                elif not final_text:
                    final_text = self.app.live_transcript
            else:
                if audio_path is None:
                    raise TranscriptionError("Could not find recorded audio to transcribe.")
                api_key = self.app.config.resolved_api_key()
                if not api_key:
                    raise TranscriptionError(
                        f"Missing API key in {self.app.config.api_key_env_var}. "
                        "Cannot transcribe recorded audio."
                    )
                self.app._update_status("Transcribing full recording...")
                self.app._update_live_status("Transcribing full recording...")
                delayed_transcriber = AudioTranscriber(api_key, model=self.app.model_menu.get())
                final_text = delayed_transcriber.transcribe(
                    str(audio_path),
                    progress_callback=lambda message, _progress: self.app._update_live_status(
                        f"Transcribing full recording... {message}"
                    ),
                )

            saved_transcript = save_transcription(final_text, str(transcript_path)) if transcript_path else ""
            self.logger.info(
                "Live recording completed (audio=%s, transcript=%s)",
                audio_path,
                saved_transcript,
            )
            self.app._replace_live_transcript(final_text)
            self.app.after(0, lambda: self.app._finish_live_recording_ui(audio_path, saved_transcript))
        except Exception as exc:
            self.logger.exception("Live recording failed while finalizing.")
            message = str(exc)
            self.app.after(0, lambda msg=message: self.app._fail_live_recording_ui(msg))

