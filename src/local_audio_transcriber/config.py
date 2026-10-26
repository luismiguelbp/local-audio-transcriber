"""Application configuration management."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from .streaming_transcriber import DEFAULT_MODEL

logger = logging.getLogger(__name__)

CONFIG_FILE = Path.home() / ".local-transcriber" / "config.json"
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
LIVE_TRANSCRIPT_MODE = "Live Transcript"
RECORD_AND_TRANSCRIBE_MODE = "Record and Transcribe"
LIVE_RECORDING_MODES = (LIVE_TRANSCRIPT_MODE, RECORD_AND_TRANSCRIBE_MODE)


def valid_env_name(value: object, default: str = "OPENAI_API_KEY") -> str:
    """Return a single environment-variable name, or the default."""
    name = str(value or "").strip()
    if _ENV_NAME.fullmatch(name):
        return name
    return default


def write_private_text(path: Path, text: str, *, private_parent: bool = False) -> None:
    """Write text so the file is readable only by the current user."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if private_parent and os.name != "nt":
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            logger.warning("Could not restrict permissions on %s", path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        file.write(text)
    if os.name != "nt":
        try:
            os.chmod(path, 0o600)
        except OSError:
            logger.warning("Could not restrict permissions on %s", path)


def load_trusted_api_env() -> None:
    """Load OpenAI key variables from the app dotenv file.

    Proxy, CA-bundle, and API-host variables in that file are ignored so a
    local dotenv file cannot redirect the API key.
    """
    env_path = CONFIG_FILE.parent / ".env"
    if not env_path.is_file():
        return
    from dotenv import dotenv_values

    for name, value in dotenv_values(env_path).items():
        if not name or not value or not _ENV_NAME.fullmatch(name):
            continue
        if "OPENAI" not in name:
            continue
        os.environ.setdefault(name, value)


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
                had_stored_secret = "api_key" in loaded_config
                loaded_config.pop("api_key", None)
                merged = {**defaults, **loaded_config}
                merged["api_key_env_var"] = valid_env_name(merged.get("api_key_env_var"))
                self.config = merged
                if had_stored_secret or self._permissions_too_open():
                    self.save()
                return merged
            except (json.JSONDecodeError, IOError):
                logger.warning("Failed to read config file %s. Using defaults.", self.config_path)
        return defaults

    def _permissions_too_open(self) -> bool:
        if os.name == "nt" or not self.config_path.exists():
            return False
        return bool(self.config_path.stat().st_mode & 0o077)

    def save(self):
        self.config.pop("api_key", None)
        write_private_text(
            self.config_path,
            json.dumps(self.config, indent=2),
            private_parent=True,
        )
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
        return valid_env_name(self.config.get("api_key_env_var"))

    @api_key_env_var.setter
    def api_key_env_var(self, value: str):
        self.config["api_key_env_var"] = valid_env_name(value)
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

