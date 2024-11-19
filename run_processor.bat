@echo off
echo Creating input and output folders if they don't exist...
if not exist "input_videos" mkdir input_videos
if not exist "output_videos" mkdir output_videos

echo Running video processor...
python process_videos.py

echo.
echo Process complete! Press any key to exit...
pause >nul