@echo off
REM run_processor.bat - Run Scene Segment Splitter headless (CLI) on Windows.
REM Missing ffmpeg/ffprobe/mkvmerge are downloaded automatically on first run.
setlocal EnableDelayedExpansion
title Scene Segment Splitter - Processor

REM Always operate from the folder this script lives in.
cd /d "%~dp0"

REM Use the project venv interpreter if present, else system python.
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

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

echo Running Scene Segment Splitter (CLI)...
echo (ffmpeg / mkvmerge will be downloaded automatically if missing)
echo.
"%PY%" scene_splitter.py --cli
if errorlevel 1 (
    echo.
    echo The processor exited with an error. Check the logs\ folder.
)
echo.
echo Done.
pause
endlocal
