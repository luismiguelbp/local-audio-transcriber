"""
Rolling streamed transcription for live recordings.

Uses the standard OpenAI audio transcriptions endpoint with stream=true on
short audio segments. This keeps live recording decoupled from any future move
to transcription-only WebSockets or Azure-specific deployments.
"""

from __future__ import annotations

import json
import logging
import queue
import tempfile
import threading
import wave
from pathlib import Path
from typing import Callable, Optional

import httpx
import numpy as np


OPENAI_TRANSCRIPTIONS_URL = "https://api.openai.com/v1/audio/transcriptions"
DEFAULT_MODEL = "gpt-4o-mini-transcribe"
ACCURATE_MODEL = "gpt-4o-transcribe"
CONTEXT_PROMPT_CHARS = 1000

DeltaCallback = Callable[[str], None]
SegmentStartCallback = Callable[[int, float, float], None]
StatusCallback = Callable[[str], None]
ErrorCallback = Callable[[str], None]
logger = logging.getLogger(__name__)


class StreamingTranscriptionError(Exception):
    """Raised when streamed transcription fails."""


def _to_pcm16(samples: np.ndarray) -> bytes:
    clipped = np.clip(samples, -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16).tobytes()


def _write_temp_wav(samples: np.ndarray, sample_rate: int) -> str:
    temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False, prefix="live_segment_")
    temp_path = temp_file.name
    temp_file.close()

    with wave.open(temp_path, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(_to_pcm16(samples))

    return temp_path


class RollingStreamingTranscriber:
    """Queue audio segments and stream transcription deltas sequentially."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        language: str = "",
        on_delta: Optional[DeltaCallback] = None,
        on_segment_start: Optional[SegmentStartCallback] = None,
        on_status: Optional[StatusCallback] = None,
        on_error: Optional[ErrorCallback] = None,
    ):
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL
        self.language = language.strip()
        self.on_delta = on_delta
        self.on_segment_start = on_segment_start
        self.on_status = on_status
        self.on_error = on_error

        self._queue: queue.Queue[tuple[np.ndarray, int, bool] | None] = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._transcript_parts: list[str] = []
        self._segment_index = 0
        self._processed_audio_seconds = 0.0

    @property
    def transcript(self) -> str:
        return "".join(self._transcript_parts).strip()

    def _context_prompt(self) -> str:
        transcript = self.transcript
        if not transcript:
            return ""
        context = transcript[-CONTEXT_PROMPT_CHARS:]
        return (
            "Previous live transcript context:\n"
            f"{context}\n\n"
            "Continue live transcribing the same meeting."
        )

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        logger.info("Started rolling streaming transcriber with model=%s", self.model)

    def add_audio_segment(self, samples: np.ndarray, sample_rate: int, final: bool = False) -> None:
        if self._stop_event.is_set():
            return
        self._queue.put((samples.copy(), sample_rate, final))

    def stop(self, wait: bool = True) -> str:
        self._stop_event.set()
        self._queue.put(None)
        if wait and self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=30)
        logger.info("Stopped rolling streaming transcriber.")
        return self.transcript

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                break

            samples, sample_rate, final = item
            if samples.size == 0:
                continue

            segment_duration = samples.size / max(1, sample_rate)
            start_seconds = self._processed_audio_seconds
            end_seconds = start_seconds + segment_duration
            self._processed_audio_seconds = end_seconds

            try:
                self._segment_index += 1
                if self.on_status is not None:
                    self.on_status("Transcribing recent audio...")
                self._transcribe_segment(
                    samples,
                    sample_rate,
                    self._segment_index,
                    start_seconds,
                    end_seconds,
                )
            except Exception as exc:
                logger.exception("Failed to transcribe live segment %s", self._segment_index)
                if self.on_error is not None:
                    self.on_error(str(exc))

            if final:
                break

        if self.on_status is not None:
            self.on_status("Live transcription stopped.")

    def _transcribe_segment(
        self,
        samples: np.ndarray,
        sample_rate: int,
        segment_index: int,
        start_seconds: float,
        end_seconds: float,
    ) -> None:
        segment_path = _write_temp_wav(samples, sample_rate)
        try:
            text_from_deltas = ""
            segment_header_sent = False
            headers = {"Authorization": f"Bearer {self.api_key}"}
            data = {
                "model": self.model,
                "stream": "true",
                "response_format": "json",
            }
            if self.language:
                data["language"] = self.language
            prompt = self._context_prompt()
            if prompt:
                data["prompt"] = prompt

            with open(segment_path, "rb") as audio_file:
                files = {"file": (Path(segment_path).name, audio_file, "audio/wav")}
                with httpx.stream(
                    "POST",
                    OPENAI_TRANSCRIPTIONS_URL,
                    headers=headers,
                    data=data,
                    files=files,
                    timeout=120,
                ) as response:
                    if response.status_code >= 400:
                        error_text = response.read().decode("utf-8", errors="replace")
                        raise StreamingTranscriptionError(
                            f"Transcription failed ({response.status_code}): {error_text}"
                        )

                    for line in response.iter_lines():
                        if not line:
                            continue
                        if line.startswith("data:"):
                            line = line[5:].strip()
                        if line == "[DONE]":
                            break

                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        event_type = event.get("type")
                        if event_type == "transcript.text.delta":
                            delta = event.get("delta", "")
                            if delta:
                                if not segment_header_sent and self.on_segment_start is not None:
                                    self.on_segment_start(segment_index, start_seconds, end_seconds)
                                    segment_header_sent = True
                                text_from_deltas += delta
                                self._transcript_parts.append(delta)
                                if self.on_delta is not None:
                                    self.on_delta(delta)
                        elif event_type == "transcript.text.done" and not text_from_deltas:
                            text = event.get("text", "")
                            if text:
                                if not segment_header_sent and self.on_segment_start is not None:
                                    self.on_segment_start(segment_index, start_seconds, end_seconds)
                                self._transcript_parts.append(text)
                                if self.on_delta is not None:
                                    self.on_delta(text)
        finally:
            try:
                Path(segment_path).unlink()
            except OSError:
                pass
