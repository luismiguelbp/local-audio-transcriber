"""
Live audio recording support.

Captures microphone audio plus Windows WASAPI loopback system audio, mixes both
sources into one WAV file, and reports per-source levels for the UI meters.
"""

from __future__ import annotations

import queue
import logging
import sys
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

try:
    import pyaudiowpatch as pyaudio
except ImportError:
    pyaudio = None


SAMPLE_RATE = 16000
BLOCK_SIZE = 1024
SAMPLE_WIDTH_BYTES = 2
CHANNELS = 1

LevelCallback = Callable[[float, float], None]
SegmentCallback = Callable[[np.ndarray, int, bool], None]
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AudioDevice:
    """Display-friendly audio device information."""

    index: int
    name: str
    hostapi: str
    channels: int
    default_samplerate: float
    is_loopback: bool = False
    backend_id: str = "sounddevice"

    @property
    def label(self) -> str:
        suffix = " (loopback)" if self.is_loopback else ""
        return f"{self.name} [{self.hostapi}]{suffix}"


class LiveRecorderError(Exception):
    """Raised when live recording cannot start or continue."""


def _hostapi_name(index: int) -> str:
    hostapis = sd.query_hostapis()
    if 0 <= index < len(hostapis):
        return str(hostapis[index]["name"])
    return "Unknown"


def _normalize_device_name(name: str) -> str:
    return " ".join(str(name).split())


def list_microphones() -> list[AudioDevice]:
    """Return input devices that can be used as microphones."""
    devices = []
    for index, device in enumerate(sd.query_devices()):
        channels = int(device.get("max_input_channels", 0))
        if channels <= 0:
            continue
        hostapi = _hostapi_name(int(device.get("hostapi", -1)))
        devices.append(
            AudioDevice(
                index=index,
                name=_normalize_device_name(device["name"]),
                hostapi=hostapi,
                channels=channels,
                default_samplerate=float(device.get("default_samplerate", SAMPLE_RATE)),
            )
        )
    return devices


def list_system_outputs() -> list[AudioDevice]:
    """Return output devices that can be monitored through loopback capture."""
    devices = []
    if sys.platform.startswith("win"):
        if pyaudio is None:
            return devices
        audio = pyaudio.PyAudio()
        try:
            for device in audio.get_loopback_device_info_generator():
                devices.append(
                    AudioDevice(
                        index=int(device["index"]),
                        name=_normalize_device_name(device["name"]),
                        hostapi="Windows loopback",
                        channels=max(1, int(device.get("maxInputChannels", 2))),
                        default_samplerate=float(device.get("defaultSampleRate", SAMPLE_RATE)),
                        is_loopback=True,
                        backend_id=str(device["index"]),
                    )
                )
        finally:
            audio.terminate()
        return devices

    return devices


def device_labels(devices: list[AudioDevice]) -> list[str]:
    """Return labels for option menus."""
    return [device.label for device in devices]


def find_device_by_label(devices: list[AudioDevice], label: str) -> Optional[AudioDevice]:
    """Find a device selected by its UI label."""
    for device in devices:
        if device.label == label:
            return device
    return None


def _mono_float32(indata: np.ndarray, frames: int) -> np.ndarray:
    if indata.size == 0:
        return np.zeros(frames, dtype=np.float32)
    data = np.asarray(indata, dtype=np.float32)
    if data.ndim > 1:
        data = data.mean(axis=1)
    return _fit_frames(data, frames)


def _fit_frames(data: np.ndarray, frames: int) -> np.ndarray:
    data = np.asarray(data, dtype=np.float32).reshape(-1)
    if len(data) == frames:
        return data
    if len(data) > frames:
        return data[:frames]
    return np.pad(data, (0, frames - len(data)))


def _resample_mono(data: np.ndarray, source_rate: int, target_rate: int, target_frames: int) -> np.ndarray:
    """Resample mono float32 audio to the app's fixed recording rate."""
    data = np.asarray(data, dtype=np.float32).reshape(-1)
    if data.size == 0:
        return np.zeros(target_frames, dtype=np.float32)
    if source_rate == target_rate:
        return _fit_frames(data, target_frames)

    source_positions = np.linspace(0.0, 1.0, num=data.size, endpoint=False)
    target_positions = np.linspace(0.0, 1.0, num=target_frames, endpoint=False)
    return np.interp(target_positions, source_positions, data).astype(np.float32)


def _loopback_channels(device: AudioDevice) -> int:
    return max(1, min(2, device.channels))


def _loopback_rate(device: AudioDevice) -> int:
    return max(8000, int(device.default_samplerate or SAMPLE_RATE))


def _loopback_frames(device: AudioDevice) -> int:
    return max(256, int(BLOCK_SIZE * (_loopback_rate(device) / SAMPLE_RATE)))


def _rms_level(data: np.ndarray) -> float:
    if data.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(data, dtype=np.float32))))
    # Map typical speech levels to a readable 0..1 meter.
    return min(1.0, rms * 8.0)


def _to_pcm16(data: np.ndarray) -> bytes:
    clipped = np.clip(data, -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16).tobytes()


def _stop_sounddevice_stream(stream: Optional[sd.InputStream], force: bool = False) -> None:
    if stream is None:
        return
    try:
        if force and hasattr(stream, "abort"):
            stream.abort()
        else:
            stream.stop()
    except Exception:
        pass
    try:
        stream.close()
    except Exception:
        pass


class LiveAudioRecorder:
    """Capture, mix, meter, segment, and record live audio."""

    def __init__(
        self,
        mic_device: Optional[AudioDevice],
        system_device: Optional[AudioDevice],
        output_path: str | Path,
        level_callback: Optional[LevelCallback] = None,
        segment_callback: Optional[SegmentCallback] = None,
        segment_seconds: int = 20,
    ):
        if mic_device is None and system_device is None:
            raise LiveRecorderError("Select at least one audio device.")

        self.mic_device = mic_device
        self.system_device = system_device
        self.output_path = Path(output_path)
        self.level_callback = level_callback
        self.segment_callback = segment_callback
        self.segment_samples = max(SAMPLE_RATE, int(segment_seconds * SAMPLE_RATE))

        self._mic_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=50)
        self._system_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=50)
        self._stop_event = threading.Event()
        self._mix_thread: Optional[threading.Thread] = None
        self._mic_stream: Optional[sd.InputStream] = None
        self._system_thread: Optional[threading.Thread] = None
        self._wave_file: Optional[wave.Wave_write] = None
        self._segment_buffer: list[np.ndarray] = []
        self._segment_buffer_samples = 0
        self._mic_pending = np.empty(0, dtype=np.float32)
        self._system_pending = np.empty(0, dtype=np.float32)
        self.started_at: Optional[float] = None

    @property
    def is_recording(self) -> bool:
        return self.started_at is not None and not self._stop_event.is_set()

    @property
    def elapsed_seconds(self) -> int:
        if self.started_at is None:
            return 0
        return int(time.monotonic() - self.started_at)

    def start(self) -> None:
        """Start audio streams and the mixer thread."""
        logger.info("Starting live audio recorder. Output path: %s", self.output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._wave_file = wave.open(str(self.output_path), "wb")
        self._wave_file.setnchannels(CHANNELS)
        self._wave_file.setsampwidth(SAMPLE_WIDTH_BYTES)
        self._wave_file.setframerate(SAMPLE_RATE)

        try:
            if self.mic_device is not None:
                self._mic_stream = self._create_mic_stream(self.mic_device, self._mic_queue)
                self._mic_stream.start()

            if self.system_device is not None:
                self._system_thread = threading.Thread(
                    target=self._system_loopback_loop,
                    args=(self.system_device, self._system_queue),
                    daemon=True,
                )
                self._system_thread.start()
        except Exception as exc:
            self.stop()
            logger.exception("Could not start audio capture.")
            raise LiveRecorderError(f"Could not start audio capture: {exc}") from exc

        self.started_at = time.monotonic()
        self._mix_thread = threading.Thread(target=self._mix_loop, daemon=True)
        self._mix_thread.start()

    def stop(self, force: bool = False) -> Path:
        """Stop all streams, flush remaining audio, and return the WAV path."""
        logger.info("Stopping live audio recorder.")
        self._stop_event.set()

        _stop_sounddevice_stream(self._mic_stream, force=force)
        self._mic_stream = None

        if self._system_thread is not None and self._system_thread.is_alive():
            self._system_thread.join(timeout=2)

        if self._mix_thread is not None and self._mix_thread.is_alive():
            self._mix_thread.join(timeout=3)

        self._flush_segment(final=True)

        if self._wave_file is not None:
            try:
                self._wave_file.close()
            finally:
                self._wave_file = None

        logger.info("Live audio saved to %s", self.output_path)
        return self.output_path

    def _create_mic_stream(
        self,
        device: AudioDevice,
        target_queue: queue.Queue[np.ndarray],
    ) -> sd.InputStream:
        def callback(indata, frames, _time_info, status):
            if status:
                # Keep recording; transient over/underflow should not stop a meeting.
                pass
            data = _mono_float32(indata, frames)
            try:
                target_queue.put_nowait(data)
            except queue.Full:
                try:
                    target_queue.get_nowait()
                    target_queue.put_nowait(data)
                except queue.Empty:
                    pass

        return sd.InputStream(
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK_SIZE,
            device=device.index,
            channels=1,
            dtype="float32",
            callback=callback,
        )

    def _system_loopback_loop(self, device: AudioDevice, target_queue: queue.Queue[np.ndarray]) -> None:
        if pyaudio is None:
            logger.warning("System audio loopback is only available on Windows.")
            return

        audio = pyaudio.PyAudio()
        stream = None
        channels = _loopback_channels(device)
        native_rate = _loopback_rate(device)
        native_frames = _loopback_frames(device)
        try:
            def callback(in_data, frame_count, _time_info, _status):
                if in_data:
                    data = np.frombuffer(in_data, dtype=np.float32).reshape(-1, channels)
                    native_mono = _mono_float32(data, frame_count)
                    mono = _resample_mono(native_mono, native_rate, SAMPLE_RATE, BLOCK_SIZE)
                    try:
                        target_queue.put_nowait(mono)
                    except queue.Full:
                        try:
                            target_queue.get_nowait()
                            target_queue.put_nowait(mono)
                        except queue.Empty:
                            pass
                return (None, pyaudio.paContinue)

            stream = audio.open(
                format=pyaudio.paFloat32,
                channels=channels,
                rate=native_rate,
                input=True,
                input_device_index=int(device.backend_id),
                frames_per_buffer=native_frames,
                stream_callback=callback,
            )
            while not self._stop_event.is_set():
                time.sleep(0.05)
        except Exception:
            # The UI will show a flat system meter if loopback capture fails.
            return
        finally:
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            audio.terminate()

    def _mix_loop(self) -> None:
        while not self._stop_event.is_set():
            mic = self._read_source_block(self._mic_queue, "_mic_pending")
            system = self._read_source_block(self._system_queue, "_system_pending")
            mixed = np.clip((mic + system) * 0.75, -1.0, 1.0).astype(np.float32)

            if self._wave_file is not None:
                self._wave_file.writeframes(_to_pcm16(mixed))

            if self.level_callback is not None:
                self.level_callback(_rms_level(mic), _rms_level(system))

            self._append_segment(mixed)
            time.sleep(BLOCK_SIZE / SAMPLE_RATE)

    def _read_source_block(self, source_queue: queue.Queue[np.ndarray], pending_attr: str) -> np.ndarray:
        pending = getattr(self, pending_attr)
        chunks = [pending] if pending.size else []

        while True:
            try:
                chunks.append(source_queue.get_nowait())
            except queue.Empty:
                break

        if chunks:
            pending = np.concatenate(chunks).astype(np.float32)

        if pending.size >= BLOCK_SIZE:
            block = pending[:BLOCK_SIZE]
            pending = pending[BLOCK_SIZE:]
        elif pending.size > 0:
            block = _fit_frames(pending, BLOCK_SIZE)
            pending = np.empty(0, dtype=np.float32)
        else:
            block = np.zeros(BLOCK_SIZE, dtype=np.float32)

        setattr(self, pending_attr, pending)
        return block

    def _append_segment(self, data: np.ndarray) -> None:
        self._segment_buffer.append(data.copy())
        self._segment_buffer_samples += len(data)
        if self._segment_buffer_samples >= self.segment_samples:
            self._flush_segment(final=False)

    def _flush_segment(self, final: bool) -> None:
        if not self._segment_buffer:
            return
        samples = np.concatenate(self._segment_buffer).astype(np.float32)
        self._segment_buffer.clear()
        self._segment_buffer_samples = 0

        if len(samples) < SAMPLE_RATE and not final:
            self._segment_buffer.append(samples)
            self._segment_buffer_samples = len(samples)
            return

        if self.segment_callback is not None:
            self.segment_callback(samples, SAMPLE_RATE, final)


class LiveAudioLevelMonitor:
    """Preview selected devices and report levels without recording."""

    def __init__(
        self,
        mic_device: Optional[AudioDevice],
        system_device: Optional[AudioDevice],
        level_callback: LevelCallback,
    ):
        self.mic_device = mic_device
        self.system_device = system_device
        self.level_callback = level_callback
        self._mic_stream: Optional[sd.InputStream] = None
        self._system_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._mic_level = 0.0
        self._system_level = 0.0

    def start(self) -> None:
        try:
            if self.mic_device is not None:
                self._mic_stream = self._create_mic_stream(self.mic_device)
                self._mic_stream.start()
            if self.system_device is not None:
                self._system_thread = threading.Thread(
                    target=self._system_loopback_loop,
                    args=(self.system_device,),
                    daemon=True,
                )
                self._system_thread.start()
        except Exception as exc:
            self.stop()
            raise LiveRecorderError(f"Could not start audio level monitor: {exc}") from exc

    def stop(self, force: bool = False) -> None:
        self._stop_event.set()
        _stop_sounddevice_stream(self._mic_stream, force=force)
        if self._system_thread is not None and self._system_thread.is_alive():
            self._system_thread.join(timeout=2)
        self._mic_stream = None
        self._system_thread = None

    def _create_mic_stream(self, device: AudioDevice) -> sd.InputStream:
        def callback(indata, frames, _time_info, status):
            if status:
                pass
            level = _rms_level(_mono_float32(indata, frames))
            self._publish_level(mic_level=level)

        return sd.InputStream(
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK_SIZE,
            device=device.index,
            channels=1,
            dtype="float32",
            callback=callback,
        )

    def _system_loopback_loop(self, device: AudioDevice) -> None:
        if pyaudio is None:
            self._publish_level(system_level=0.0)
            logger.warning("System audio level monitoring is only available on Windows.")
            return

        audio = pyaudio.PyAudio()
        stream = None
        channels = _loopback_channels(device)
        native_rate = _loopback_rate(device)
        native_frames = _loopback_frames(device)
        try:
            def callback(in_data, frame_count, _time_info, _status):
                if in_data:
                    data = np.frombuffer(in_data, dtype=np.float32).reshape(-1, channels)
                    self._publish_level(system_level=_rms_level(_mono_float32(data, frame_count)))
                return (None, pyaudio.paContinue)

            stream = audio.open(
                format=pyaudio.paFloat32,
                channels=channels,
                rate=native_rate,
                input=True,
                input_device_index=int(device.backend_id),
                frames_per_buffer=native_frames,
                stream_callback=callback,
            )
            while not self._stop_event.is_set():
                time.sleep(0.05)
        except Exception:
            self._publish_level(system_level=0.0)
        finally:
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            audio.terminate()

    def _publish_level(
        self,
        mic_level: Optional[float] = None,
        system_level: Optional[float] = None,
    ) -> None:
        with self._lock:
            if mic_level is not None:
                self._mic_level = mic_level
            if system_level is not None:
                self._system_level = system_level
            current_mic = self._mic_level
            current_system = self._system_level
        self.level_callback(current_mic, current_system)
