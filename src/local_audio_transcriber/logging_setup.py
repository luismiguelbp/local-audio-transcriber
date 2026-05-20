"""Centralized logging setup for Local Audio Transcriber."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

APP_HOME_DIR = Path.home() / ".local-transcriber"
LOG_FILE_NAME = "application.log"
_CONFIGURED_FLAG = "_local_audio_transcriber_logging_configured"


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
    log_file = log_dir / LOG_FILE_NAME
    root_logger = logging.getLogger()

    if force:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
            handler.close()
        setattr(root_logger, _CONFIGURED_FLAG, False)

    if getattr(root_logger, _CONFIGURED_FLAG, False):
        return log_dir

    formatter = logging.Formatter(
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

    root_logger.setLevel(level)
    root_logger.addHandler(file_handler)
    setattr(root_logger, _CONFIGURED_FLAG, True)
    logging.captureWarnings(True)
    logging.getLogger(__name__).info("Logging initialized. Log file: %s", log_file)
    return log_dir
