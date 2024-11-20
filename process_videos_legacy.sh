#!/bin/bash

set -e

# Set directories
BIN_DIR="$(dirname "$0")/bin"
mkdir -p "$BIN_DIR"

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check if FFmpeg is present
if [ ! -f "$BIN_DIR/ffmpeg" ]; then
    echo "FFmpeg not found. Downloading FFmpeg..."

    # Get the latest FFmpeg static build URL for your OS
    OS_TYPE="$(uname -s)"
    if [ "$OS_TYPE" = "Darwin" ]; then
        # macOS
        FFMPEG_URL="https://evermeet.cx/ffmpeg/ffmpeg.zip"
        OUTPUT="$BIN_DIR/ffmpeg.zip"
        curl -L -o "$OUTPUT" "$FFMPEG_URL"
        unzip -o "$OUTPUT" -d "$BIN_DIR"
        rm "$OUTPUT"
    else
        # Assume Linux
        FFMPEG_URL=$(curl -s https://johnvansickle.com/ffmpeg/ | grep -oP 'href="\Kffmpeg-release-amd64-static\.tar\.xz(?=")' | head -n 1)
        FFMPEG_URL="https://johnvansickle.com/ffmpeg/$FFMPEG_URL"
        OUTPUT="$BIN_DIR/ffmpeg.tar.xz"
        curl -L -o "$OUTPUT" "$FFMPEG_URL"
        tar -xf "$OUTPUT" -C "$BIN_DIR"
        cp "$BIN_DIR"/ffmpeg-*-amd64-static/ffmpeg "$BIN_DIR"
        cp "$BIN_DIR"/ffmpeg-*-amd64-static/ffprobe "$BIN_DIR"
        rm -rf "$BIN_DIR"/ffmpeg-*-amd64-static
        rm "$OUTPUT"
    fi

    chmod +x "$BIN_DIR/ffmpeg"
    chmod +x "$BIN_DIR/ffprobe"
else
    echo "FFmpeg found."
fi

# Check if mkvmerge is present
if [ ! -f "$BIN_DIR/mkvmerge" ]; then
    echo "MKVToolNix not found. Downloading MKVToolNix..."

    # Get the latest MKVToolNix release URL for your OS
    OS_TYPE="$(uname -s)"
    if [ "$OS_TYPE" = "Darwin" ]; then
        # macOS
        MKV_URL=$(curl -s https://mkvtoolnix.download/macos/ | grep -oP 'href="\Khttps://mkvtoolnix.download/macos/mkvtoolnix-.*\.dmg(?=")' | head -n 1)
        OUTPUT="$BIN_DIR/mkvtoolnix.dmg"
        curl -L -o "$OUTPUT" "$MKV_URL"
        hdiutil attach "$OUTPUT" -mountpoint "/Volumes/mkvtoolnix"
        cp "/Volumes/mkvtoolnix/mkvtoolnix.app/Contents/MacOS/mkvmerge" "$BIN_DIR"
        hdiutil detach "/Volumes/mkvtoolnix"
        rm "$OUTPUT"
    else
        # Assume Linux
        MKV_URL=$(curl -s https://mkvtoolnix.download/downloads.html | grep -oP 'https://mkvtoolnix.download/appimage/MKVToolNix_GUI-\K[^\"]+(?=\.x86_64.AppImage)' | head -n 1)
        MKV_URL="https://mkvtoolnix.download/appimage/MKVToolNix_GUI-$MKV_URL.x86_64.AppImage"
        OUTPUT="$BIN_DIR/mkvtoolnix.appimage"
        curl -L -o "$OUTPUT" "$MKV_URL"
        chmod +x "$OUTPUT"
        "$OUTPUT" --appimage-extract
        cp squashfs-root/usr/bin/mkvmerge "$BIN_DIR"
        rm -rf squashfs-root
        rm "$OUTPUT"
    fi

    chmod +x "$BIN_DIR/mkvmerge"
else
    echo "MKVToolNix found."
fi

# Create the directories if they don't exist
echo "Creating input and output folders if they don't exist..."
mkdir -p input_videos
mkdir -p output_videos

# Run the Python script
echo "Running video processor..."
python3 process_videos.py

# Inform the user that the process is complete
echo
echo "Process complete! Press Enter to exit..."
read -n 1
