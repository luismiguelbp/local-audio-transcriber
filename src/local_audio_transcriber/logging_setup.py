"""Centralized logging setup for Local Audio Transcriber."""

from __future__ import annotations

import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

_SECRET_PATTERN = re.compile(r"(?i)bearer\s+\S+|\bsk-[A-Za-z0-9_-]{8,}\b")

APP_HOME_DIR = Path.home() / ".local-transcriber"
LOG_FILE_NAME = "application.log"
_CONFIGURED_FLAG = "_local_audio_transcriber_logging_configured"


def redact_text(text: str) -> str:
    """Remove bearer tokens and OpenAI-style API keys from text."""
    return _SECRET_PATTERN.sub("[redacted]", text)


class _RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record))


def get_log_directory(app_home_dir: Optional[Path] = None) -> Path:
    """Return the directory where application logs are stored."""
    base_dir = app_home_dir or APP_HOME_DIR
    return base_dir / "logs"


def setup_logging(
    app_home_dir: Optional[Path] = None,
    level: int = logging.INFO,
    force: bool = False,
) -> Path:
    """Configure root logging with a rotating file in the app log directory."""
    log_dir = get_log_directory(app_home_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        try:
            os.chmod(log_dir, 0o700)
        except OSError:
            logging.getLogger(__name__).warning("Could not restrict permissions on %s", log_dir)
    log_file = log_dir / LOG_FILE_NAME
    root_logger = logging.getLogger()

    if force:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
            handler.close()
        setattr(root_logger, _CONFIGURED_FLAG, False)

    if getattr(root_logger, _CONFIGURED_FLAG, False):
        return log_dir

    formatter = _RedactingFormatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    if os.name != "nt" and log_file.exists():
        try:
            os.chmod(log_file, 0o600)
        except OSError:
            logging.getLogger(__name__).warning("Could not restrict permissions on %s", log_file)

    root_logger.setLevel(level)
    root_logger.addHandler(file_handler)
    setattr(root_logger, _CONFIGURED_FLAG, True)
    logging.captureWarnings(True)
    logging.getLogger(__name__).info("Logging initialized. Log file: %s", log_file)
    return log_dir
