"""Local Audio Transcriber package."""


def main() -> None:
    """Package-level launcher that defers GUI imports until runtime."""
    from .__main__ import main as package_main

    package_main()


__all__ = ["main"]
