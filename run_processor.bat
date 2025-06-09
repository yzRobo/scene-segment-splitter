@echo off
setlocal EnableDelayedExpansion

:: Set directories
set "SCRIPT_DIR=%~dp0"
set "BIN_DIR=%SCRIPT_DIR%bin"
set "SEVEN_ZIP_DIR=%BIN_DIR%\7zip"
set "TEMP_DIR=%SCRIPT_DIR%temp_extract"

:: Create bin directory if it doesn't exist
if not exist "%BIN_DIR%" (
    mkdir "%BIN_DIR%"
)

:: Create temporary extraction directory
if not exist "%TEMP_DIR%" (
    mkdir "%TEMP_DIR%"
)

:: Download and install 7-Zip if not present
if not exist "%SEVEN_ZIP_DIR%\7z.exe" (
    echo 7-Zip not found. Downloading and installing 7-Zip...
    pause

    :: Download 7-Zip installer
    powershell -Command "Invoke-WebRequest -Uri 'https://www.7-zip.org/a/7z2408-x64.exe' -OutFile '%BIN_DIR%\7z_setup.exe'"

    :: Install 7-Zip silently to SEVEN_ZIP_DIR
    "%BIN_DIR%\7z_setup.exe" /S /D="%SEVEN_ZIP_DIR%"

    :: Clean up installer
    del "%BIN_DIR%\7z_setup.exe"

    if not exist "%SEVEN_ZIP_DIR%\7z.exe" (
        echo Failed to install 7-Zip. Please check your internet connection or try again later.
        pause
        exit /b 1
    )
    echo 7-Zip installed successfully.
    pause
) else (
    echo 7-Zip found.
    pause
)

:: Check if FFmpeg is present
if not exist "%BIN_DIR%\ffmpeg.exe" (
    echo FFmpeg not found. Downloading FFmpeg...
    pause

    :: Download FFmpeg using direct link
    powershell -Command "Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile '%BIN_DIR%\ffmpeg.zip'"

    :: Extract FFmpeg
    powershell -Command "Expand-Archive -Path '%BIN_DIR%\ffmpeg.zip' -DestinationPath '%BIN_DIR%' -Force"

    :: Copy ffmpeg.exe and ffprobe.exe to bin directory
    for /d %%i in ("%BIN_DIR%\ffmpeg-*") do (
        copy "%%i\bin\ffmpeg.exe" "%BIN_DIR%" >nul
        copy "%%i\bin\ffprobe.exe" "%BIN_DIR%" >nul
    )

    :: Clean up
    del "%BIN_DIR%\ffmpeg.zip"
    for /d %%i in ("%BIN_DIR%\ffmpeg-*") do (
        rd /s /q "%%i"
    )

    echo FFmpeg downloaded and extracted successfully.
    pause
) else (
    echo FFmpeg found.
    pause
)

:: Check if MKVToolNix is present
set "MKVMERGE_COPIED=0"
if not exist "%BIN_DIR%\mkvmerge.exe" (
    echo MKVToolNix not found. Downloading MKVToolNix...
    pause

    :: Download MKVToolNix .7z archive
    powershell -Command "Invoke-WebRequest -Uri 'https://mkvtoolnix.download/windows/releases/88.0/mkvtoolnix-64-bit-88.0.7z' -OutFile '%BIN_DIR%\mkvtoolnix.7z'"

    :: Extract MKVToolNix using 7z.exe into TEMP_DIR
    echo Extracting MKVToolNix...
    "%SEVEN_ZIP_DIR%\7z.exe" x "%BIN_DIR%\mkvtoolnix.7z" -o"%TEMP_DIR%" -y
    pause

    :: List contents of extracted folder
    echo Listing contents of "%TEMP_DIR%":
    dir "%TEMP_DIR%" /b
    pause

    :: Try to copy mkvmerge.exe from expected paths
    if exist "%TEMP_DIR%\mkvtoolnix\mkvmerge.exe" (
        echo mkvmerge.exe found at "%TEMP_DIR%\mkvtoolnix\mkvmerge.exe"
        copy "%TEMP_DIR%\mkvtoolnix\mkvmerge.exe" "%BIN_DIR%"
        if errorlevel 1 (
            echo Failed to copy mkvmerge.exe to bin directory.
            pause
            exit /b 1
        )
        echo mkvmerge.exe copied to bin directory.
        set "MKVMERGE_COPIED=1"
    ) else (
        for /d %%d in ("%TEMP_DIR%\mkvtoolnix-*") do (
            if exist "%%d\mkvmerge.exe" (
                echo mkvmerge.exe found at "%%d\mkvmerge.exe"
                copy "%%d\mkvmerge.exe" "%BIN_DIR%"
                if errorlevel 1 (
                    echo Failed to copy mkvmerge.exe to bin directory.
                    pause
                    exit /b 1
                )
                echo mkvmerge.exe copied to bin directory.
                set "MKVMERGE_COPIED=1"
            )
        )
    )

    :: Recursive search if not found yet
    if !MKVMERGE_COPIED! EQU 0 (
        echo mkvmerge.exe not found in expected directories.
        echo Searching recursively...
        set "FOUND=0"
        for /r "%TEMP_DIR%" %%f in (mkvmerge.exe) do (
            if !FOUND! EQU 0 (
                echo mkvmerge.exe found at "%%f"
                copy "%%f" "%BIN_DIR%"
                if errorlevel 1 (
                    echo Failed to copy mkvmerge.exe to bin directory.
                    pause
                    exit /b 1
                )
                echo mkvmerge.exe copied to bin directory.
                set "MKVMERGE_COPIED=1"
                set "FOUND=1"
            )
        )
    )

    if !MKVMERGE_COPIED! EQU 0 (
        echo Failed to find mkvmerge.exe. Please check the archive and try again.
        pause
        exit /b 1
    )

    :: Clean up
    del "%BIN_DIR%\mkvtoolnix.7z"
    rd /s /q "%TEMP_DIR%"

    echo MKVToolNix downloaded and extracted successfully.
    pause
) else (
    echo MKVToolNix found.
    pause
)

echo Creating input and output folders if they don't exist...
if not exist "input_videos" mkdir "input_videos"
if not exist "output_videos" mkdir "output_videos"
pause

echo Running video processor...
python process_videos.py
pause

echo.
echo Process complete! Press any key to exit...
pause >nul
