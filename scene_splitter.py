#!/usr/bin/env python3
"""
scene_splitter.py - Scene Segment Splitter Main Launcher

This is the main entry point for the Scene Segment Splitter application.
It can run in two modes:

1. GUI Mode (default): Launches the graphical user interface
   Usage: python scene_splitter.py

2. CLI Mode: Runs the command-line version for batch processing
   Usage: python scene_splitter.py --cli [options]
   
Command-line options:
  --cli              Run in command-line mode (no GUI)
  --input PATH       Input folder path (default: input_videos)
  --output PATH      Output folder path (default: output_videos)
  --csv FILE         Episode list CSV file (default: episode_list.csv)
  --intro-duration N Intro duration in seconds (default: 47)

Examples:
  python scene_splitter.py                    # Launch GUI
  python scene_splitter.py --cli             # Run with defaults
  python scene_splitter.py --cli --input /path/to/videos --intro-duration 60
"""

import sys
import argparse
import os

def main():
    parser = argparse.ArgumentParser(description='Scene Segment Splitter - Split video files containing multiple episodes')
    parser.add_argument('--cli', action='store_true', help='Run in command-line mode (no GUI)')
    parser.add_argument('--input', type=str, default='input_videos', help='Input folder path')
    parser.add_argument('--output', type=str, default='output_videos', help='Output folder path')
    parser.add_argument('--csv', type=str, default='episode_list.csv', help='Episode list CSV file')
    parser.add_argument('--intro-duration', type=int, default=47, help='Intro duration in seconds')
    
    args = parser.parse_args()
    
    if args.cli:
        # Run in command-line mode
        print("Running in command-line mode...")
        from process_videos import VideoProcessor, setup_logging
        from datetime import datetime
        
        log_file = setup_logging()
        print(f"Starting video processing at {datetime.now()}")
        print(f"Log file: {log_file}")
        
        processor = VideoProcessor(args.input, args.output)
        processor.INTRO_DURATION = args.intro_duration
        
        # Load custom episode list if specified
        if args.csv != 'episode_list.csv':
            processor.episode_map = processor._load_episode_list(args.csv)
            
        processor.process_videos()
        print(f"Processing completed at {datetime.now()}")
    else:
        # Run GUI mode
        print("Starting GUI mode...")
        try:
            import tkinter as tk
            from gui import VideoSplitterGUI, main as gui_main
            gui_main()
        except ImportError as e:
            print(f"Error: Could not import GUI components: {e}")
            print("Make sure tkinter is installed. On Ubuntu/Debian: sudo apt-get install python3-tk")
            print("Falling back to command-line mode...")
            print("Run with --cli flag to suppress this message")
            sys.exit(1)

if __name__ == "__main__":
    main()