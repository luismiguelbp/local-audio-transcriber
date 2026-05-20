"""Module entrypoint for ``python -m local_audio_transcriber``."""

from .logging_setup import setup_logging


def main() -> None:
    """Initialize logging, then start the GUI application."""
    setup_logging()
    from .app import main as app_main

    app_main()


if __name__ == "__main__":
    main()
