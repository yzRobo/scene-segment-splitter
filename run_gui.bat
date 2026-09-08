@echo off
REM run_gui.bat - Launch the Scene Segment Splitter GUI on Windows.
setlocal EnableDelayedExpansion
title Scene Segment Splitter - GUI

REM Always run from the folder this script lives in.
cd /d "%~dp0"

REM Pick an interpreter: project venv first, then system python.
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

echo Checking Python...
"%PY%" --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not on PATH.
    echo Install Python 3.10+ from https://www.python.org/
    pause
    exit /b 1
)

REM Create the working folders if missing.
for %%D in (input_videos output_videos configs logs episode_lists) do (
    if not exist "%%D" mkdir "%%D"
)

REM Install/refresh optional dependencies (the modern theme). Harmless if present.
if exist "requirements.txt" (
    "%PY%" -m pip install --quiet --disable-pip-version-check -r requirements.txt >nul 2>&1
)

REM ffmpeg / ffprobe / mkvmerge are downloaded automatically on first launch
REM (see bootstrap.py); no manual setup needed.

echo Launching Scene Segment Splitter...
"%PY%" scene_splitter.py
if errorlevel 1 (
    echo.
    echo The application exited with an error. Check the logs\ folder.
    pause
)
endlocal
