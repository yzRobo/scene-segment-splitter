#!/usr/bin/env bash
# run_gui.sh - Launch the Scene Segment Splitter GUI on macOS / Linux.
set -e
cd "$(dirname "$0")"

# Pick an interpreter: project venv first, then python3.
PY="python3"
if [ -x ".venv/bin/python" ]; then
    PY=".venv/bin/python"
fi

if ! "$PY" --version >/dev/null 2>&1; then
    echo "ERROR: python3 not found. Install Python 3.10+."
    exit 1
fi

# Create working folders.
mkdir -p input_videos output_videos configs logs episode_lists

# Install optional dependencies (modern theme). Ignore failures.
if [ -f requirements.txt ]; then
    "$PY" -m pip install --quiet --disable-pip-version-check -r requirements.txt >/dev/null 2>&1 || true
fi

# On Windows the app auto-downloads ffmpeg/mkvmerge. On macOS/Linux, static
# builds vary by distro, so install them via your package manager if missing.
if [ ! -x "bin/mkvmerge" ] && ! command -v mkvmerge >/dev/null 2>&1; then
    echo "NOTE: ffmpeg/ffprobe/mkvmerge not found in bin/ or on PATH."
    echo "Install them with your package manager, for example:"
    echo "  macOS:  brew install ffmpeg mkvtoolnix"
    echo "  Debian: sudo apt-get install ffmpeg mkvtoolnix"
fi

# tkinter check (commonly missing on Linux).
if ! "$PY" -c "import tkinter" >/dev/null 2>&1; then
    echo "ERROR: tkinter is not available."
    echo "On Debian/Ubuntu: sudo apt-get install python3-tk"
    exit 1
fi

exec "$PY" scene_splitter.py
