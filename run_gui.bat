@echo off
REM run_gui.bat - Scene Segment Splitter GUI Launcher for Windows
REM This batch file launches the GUI version of Scene Segment Splitter
REM It checks for Python installation and creates necessary directories

setlocal EnableDelayedExpansion

:: Set window title
title Scene Segment Splitter - GUI

:: Check if Python is installed
echo Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH!
    echo Please install Python 3.10 or later from https://www.python.org/
    pause
    exit /b 1
)

:: Create necessary directories if they don't exist
echo Setting up directories...

if not exist "input_videos" (
    mkdir "input_videos"
    echo Created input_videos folder
)

if not exist "output_videos" (
    mkdir "output_videos"
    echo Created output_videos folder
)

if not exist "configs" (
    mkdir "configs"
    echo Created configs folder for saving configuration files
)

if not exist "logs" (
    mkdir "logs"
    echo Created logs folder
)

if not exist "episode_lists" (
    mkdir "episode_lists"
    echo Created episode_lists folder for episode CSV files
)

:: Check if the GUI script exists
if not exist "scene_splitter.py" (
    echo ERROR: scene_splitter.py not found!
    echo Please ensure all files are properly extracted.
    pause
    exit /b 1
)

:: Install dependencies if requirements.txt exists and user agrees
if exist "requirements.txt" (
    echo.
    echo Checking dependencies...
    python -m pip show tkinter >nul 2>&1
    if errorlevel 1 (
        echo tkinter is not available. Installing dependencies...
        python -m pip install -r requirements.txt
    )
)

:: Launch the GUI
echo.
echo Launching Scene Segment Splitter GUI...
echo.
python scene_splitter.py

:: Check if the script exited with an error
if errorlevel 1 (
    echo.
    echo ERROR: The application encountered an error!
    echo Check the logs folder for details.
    pause
)

endlocal