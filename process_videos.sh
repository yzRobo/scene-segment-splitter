#!/bin/bash

# Print message
echo "Creating input and output folders if they don't exist..."

# Create the directories if they don't exist
mkdir -p input_videos
mkdir -p output_videos

# Run the Python script
echo "Running video processor..."
python3 process_videos.py

# Inform the user that the process is complete
echo
echo "Process complete! Press Enter to exit..."
read -n 1