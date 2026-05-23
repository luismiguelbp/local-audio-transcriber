#!/usr/bin/env sh
set -eu

export PATH="/usr/local/bin:/opt/homebrew/bin:$HOME/.local/bin:$PATH"

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT" || exit 1

"${SCRIPT_DIR}/install-local-audio-transcriber.sh"

nohup "$PROJECT_ROOT/.venv/bin/python" -m local_audio_transcriber \
  >"$PROJECT_ROOT/.local-audio-transcriber-launch.log" 2>&1 &

echo "Local Audio Transcriber started. You can close this Terminal window."
