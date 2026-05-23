"""Application configuration management."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from .streaming_transcriber import DEFAULT_MODEL

logger = logging.getLogger(__name__)

CONFIG_FILE = Path.home() / ".local-transcriber" / "config.json"
LIVE_TRANSCRIPT_MODE = "Live Transcript"
RECORD_AND_TRANSCRIBE_MODE = "Record and Transcribe"
LIVE_RECORDING_MODES = (LIVE_TRANSCRIPT_MODE, RECORD_AND_TRANSCRIBE_MODE)


class ConfigManager:
    """Manage persistent application configuration."""

    def __init__(self):
        self.config_path = CONFIG_FILE
        self.config = self._load_config()

    def _load_config(self) -> dict:
        defaults = {
            "output_dir": str(Path.home() / "Documents" / "Transcriptions"),
            "theme": "System",
            "api_key_env_var": "OPENAI_API_KEY",
            "mic_device": "",
            "system_device": "",
            "transcription_model": DEFAULT_MODEL,
            "live_recording_mode": LIVE_TRANSCRIPT_MODE,
        }
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as file:
                    loaded_config = json.load(file)
                loaded_config.pop("api_key", None)
                return {**defaults, **loaded_config}
            except (json.JSONDecodeError, IOError):
                logger.warning("Failed to read config file %s. Using defaults.", self.config_path)
        return defaults

    def save(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as file:
            json.dump(self.config, file, indent=2)
        logger.info("Configuration saved to %s", self.config_path)

    @property
    def output_dir(self) -> str:
        return self.config.get("output_dir", str(Path.home() / "Documents" / "Transcriptions"))

    @output_dir.setter
    def output_dir(self, value: str):
        self.config["output_dir"] = value
        self.save()

    @property
    def mic_device(self) -> str:
        return self.config.get("mic_device", "")

    @mic_device.setter
    def mic_device(self, value: str):
        self.config["mic_device"] = value
        self.save()

    @property
    def system_device(self) -> str:
        return self.config.get("system_device", "")

    @system_device.setter
    def system_device(self, value: str):
        self.config["system_device"] = value
        self.save()

    @property
    def transcription_model(self) -> str:
        return self.config.get("transcription_model", DEFAULT_MODEL)

    @transcription_model.setter
    def transcription_model(self, value: str):
        self.config["transcription_model"] = value
        self.save()

    @property
    def live_recording_mode(self) -> str:
        value = str(self.config.get("live_recording_mode", LIVE_TRANSCRIPT_MODE)).strip()
        if value not in LIVE_RECORDING_MODES:
            return LIVE_TRANSCRIPT_MODE
        return value

    @live_recording_mode.setter
    def live_recording_mode(self, value: str):
        normalized = str(value).strip()
        if normalized not in LIVE_RECORDING_MODES:
            normalized = LIVE_TRANSCRIPT_MODE
        self.config["live_recording_mode"] = normalized
        self.save()

    @property
    def theme(self) -> str:
        value = str(self.config.get("theme", "System")).strip().title()
        if value not in {"System", "White", "Dark"}:
            return "System"
        return value

    @theme.setter
    def theme(self, value: str):
        normalized = str(value).strip().title()
        if normalized not in {"System", "White", "Dark"}:
            normalized = "System"
        self.config["theme"] = normalized
        self.save()

    @property
    def api_key_env_var(self) -> str:
        value = str(self.config.get("api_key_env_var", "OPENAI_API_KEY")).strip()
        return value or "OPENAI_API_KEY"

    @api_key_env_var.setter
    def api_key_env_var(self, value: str):
        normalized = str(value).strip() or "OPENAI_API_KEY"
        self.config["api_key_env_var"] = normalized
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

