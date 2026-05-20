#!/bin/bash
# Local Audio Transcriber launcher for macOS
# Double-click this file in Finder to install (if needed) and start the app.

export PATH="/usr/local/bin:/opt/homebrew/bin:$HOME/.local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "${SCRIPT_DIR}/launch-local-audio-transcriber.sh"
