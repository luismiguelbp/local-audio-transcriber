#!/usr/bin/env bash
set -euo pipefail

export PATH="/usr/local/bin:/opt/homebrew/bin:$HOME/.local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

VENV_DIR=".venv"
VENV_PYTHON="$VENV_DIR/bin/python"
SETUP_MARKER="$VENV_DIR/.local_audio_transcriber_setup_complete"
BASE_PYTHON=""

select_base_python() {
  local candidate
  for candidate in python3.12 python3.11 python3.10 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c "import tkinter" >/dev/null 2>&1; then
        BASE_PYTHON="$candidate"
        return 0
      fi
    fi
  done
  return 1
}

venv_has_tkinter() {
  "$VENV_PYTHON" -c "import tkinter" >/dev/null 2>&1
}

create_venv() {
  "$BASE_PYTHON" -m venv "$VENV_DIR"
  if [ ! -x "$VENV_PYTHON" ]; then
    echo
    echo "Venv creation completed but python executable was not found."
    echo
    return 1
  fi
  if ! venv_has_tkinter; then
    echo
    echo "Created venv still does not include tkinter."
    echo "Install Python with Tcl/Tk support (python.org or Homebrew python-tk)."
    echo
    return 1
  fi
}

setup_failed() {
  echo
  echo "Failed to install dependencies automatically."
  echo "Run these commands manually in \"$PROJECT_ROOT\":"
  echo "  $VENV_PYTHON -m pip install -r requirements.txt"
  echo "  $VENV_PYTHON -m pip install -e ."
  echo
  exit 1
}

venv_tk_patchlevel() {
  "$VENV_PYTHON" -c "
import tkinter as tk
root = tk.Tk()
try:
    print(root.tk.call('info', 'patchlevel'))
finally:
    root.destroy()
"
}

venv_tkdnd_works() {
  "$VENV_PYTHON" -c "
import tkinter
from tkinterdnd2 import TkinterDnD

root = tkinter.Tk()
root.withdraw()
try:
    TkinterDnD._require(root)
except Exception:
    raise SystemExit(1)
finally:
    root.destroy()
" >/dev/null 2>&1
}

patch_tkdnd_for_tcl9() {
  if [ "$(uname -s)" != "Darwin" ]; then
    return 0
  fi

  local patchlevel
  patchlevel="$(venv_tk_patchlevel)"
  case "$patchlevel" in
    9.*) ;;
    *) return 0 ;;
  esac

  if venv_tkdnd_works; then
    return 0
  fi

  echo "Patching tkinterdnd2 for Tcl/Tk 9..."

  local arch tkdnd_archive platform_dir tkdnd_url tkdnd_dir tmpdir
  arch="$(uname -m)"
  case "$arch" in
    arm64)
      tkdnd_archive="tkdnd-2.9.5-macOS-tcl9.0-arm64-x64-14.2.1.tgz"
      platform_dir="osx-arm64"
      ;;
    x86_64)
      tkdnd_archive="tkdnd-2.9.5-macOS-tcl9.0-x86_64-x64-14.2.1.tgz"
      platform_dir="osx-x64"
      ;;
    *)
      echo "Unsupported macOS architecture for tkdnd patch: $arch"
      return 1
      ;;
  esac

  tkdnd_url="https://github.com/petasis/tkdnd/releases/download/tkdnd-release-test-v2.9.5/${tkdnd_archive}"
  tkdnd_dir="$("$VENV_PYTHON" -c "import os, tkinterdnd2; print(os.path.join(os.path.dirname(tkinterdnd2.__file__), 'tkdnd', '${platform_dir}'))")"
  tmpdir="$(mktemp -d)"

  if ! curl -fsSL -o "$tmpdir/$tkdnd_archive" "$tkdnd_url"; then
    rm -rf "$tmpdir"
    echo "Failed to download tkdnd update from GitHub."
    return 1
  fi

  tar -xzf "$tmpdir/$tkdnd_archive" -C "$tmpdir"
  cp -a "$tmpdir/tkdnd2.9.5/"* "$tkdnd_dir/"
  rm -rf "$tmpdir"

  if ! venv_tkdnd_works; then
    echo "tkdnd patch applied but drag-and-drop still does not load."
    return 1
  fi

  echo "tkinterdnd2 patched for Tcl/Tk 9."
}

if ! select_base_python; then
  echo
  echo "Could not find a Python interpreter with tkinter support."
  echo "Install Python from python.org or Homebrew, then run this installer again."
  echo "Suggested:"
  echo "  brew install python@3.12 python-tk@3.12"
  echo
  exit 1
fi

if [ ! -x "$VENV_PYTHON" ]; then
  echo "Virtual environment not found. Creating \"$VENV_DIR\"..."
  create_venv || exit 1
fi

if ! venv_has_tkinter; then
  echo "Existing venv python has no tkinter. Recreating venv with: $BASE_PYTHON"
  rm -rf "$VENV_DIR"
  create_venv || exit 1
fi

if [ ! -f "$SETUP_MARKER" ]; then
  echo "Running first-time setup..."
  "$VENV_PYTHON" -m pip install --upgrade pip || setup_failed
  "$VENV_PYTHON" -m pip install -r requirements.txt || setup_failed
  "$VENV_PYTHON" -m pip install -e . || setup_failed
  : > "$SETUP_MARKER"
else
  if ! "$VENV_PYTHON" -c "import openai, customtkinter, pydub, dotenv" >/dev/null 2>&1; then
    echo "Missing dependencies detected. Reinstalling..."
    "$VENV_PYTHON" -m pip install -r requirements.txt || setup_failed
    "$VENV_PYTHON" -m pip install -e . || setup_failed
    : > "$SETUP_MARKER"
  fi
fi

if ! patch_tkdnd_for_tcl9; then
  echo
  echo "Warning: file drag-and-drop may not work on this Python/Tcl/Tk setup."
  echo "You can still add files with the Add Audio Files button."
  echo
fi

echo "Installation/setup completed successfully."
