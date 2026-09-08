#!/usr/bin/env python3
"""
scene_splitter.py - Scene Segment Splitter launcher

GUI mode (default):
    python scene_splitter.py

CLI mode:
    python scene_splitter.py --cli [options]

CLI options:
    --cli                 Run headless (no GUI)
    --config FILE         Load a JSON config profile (configs/*.json)
    --input PATH          Input folder (default: input_videos)
    --output PATH         Output folder (default: output_videos)
    --csv FILE            Episode list CSV (default: episode_list.csv)
    --intro-duration N    Intro duration in seconds
    --target-time N       Manual boundary time (implies --no-auto-target)
    --time-margin N       Search margin around the boundary (seconds)
    --no-auto-target      Disable runtime-derived boundary (use --target-time)
    --detection-method M  Detection method (see README)
    --on-failure MODE     copy | midpoint | skip  (default: copy)

Examples:
    python scene_splitter.py
    python scene_splitter.py --cli --config configs/hey_arnold_config.json
    python scene_splitter.py --cli --input D:/in --output D:/out --csv show.csv
"""

import os
import sys
import json
import argparse


def _load_config_file(path):
    if not path:
        return {}
    if not os.path.exists(path):
        print(f"ERROR: config file not found: {path}")
        sys.exit(2)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_cli(args):
    from datetime import datetime
    from process_videos import VideoProcessor, setup_logging

    config = _load_config_file(args.config)

    # Command-line flags override the config file.
    if args.input is not None:
        config["input_folder"] = args.input
    if args.output is not None:
        config["output_folder"] = args.output
    if args.csv is not None:
        if not os.path.exists(args.csv):
            print(f"ERROR: episode CSV not found: {args.csv}")
            sys.exit(2)
        config["episode_csv"] = args.csv
    if args.intro_duration is not None:
        config["intro_duration"] = args.intro_duration
    if args.target_time is not None:
        config["target_time"] = args.target_time
        config["auto_target"] = False
    if args.time_margin is not None:
        config["time_margin"] = args.time_margin
    if args.no_auto_target:
        config["auto_target"] = False
    if args.detection_method is not None:
        config["detection_method"] = args.detection_method
    if args.on_failure is not None:
        config["on_detection_failure"] = args.on_failure

    input_folder = config.get("input_folder", "input_videos")
    output_folder = config.get("output_folder", "output_videos")

    log_file = setup_logging()
    print(f"Scene Segment Splitter (CLI) - starting {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"Log file: {log_file}")
    try:
        processor = VideoProcessor(input_folder, output_folder, config=config)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    processor.process_videos()
    print(f"Done - {datetime.now():%Y-%m-%d %H:%M:%S}")


def run_gui():
    try:
        import tkinter  # noqa: F401
        from gui import main as gui_main
    except ImportError as e:
        print(f"Could not start the GUI ({e}).")
        print("tkinter may be missing. On Ubuntu/Debian: sudo apt-get install python3-tk")
        print("You can still run headless: python scene_splitter.py --cli")
        sys.exit(1)
    gui_main()


def main():
    parser = argparse.ArgumentParser(
        description="Scene Segment Splitter - split multi-episode video files")
    parser.add_argument("--cli", action="store_true", help="Run headless (no GUI)")
    parser.add_argument("--config", type=str, help="JSON config profile to load")
    parser.add_argument("--input", type=str, help="Input folder path")
    parser.add_argument("--output", type=str, help="Output folder path")
    parser.add_argument("--csv", type=str, help="Episode list CSV file")
    parser.add_argument("--intro-duration", type=int, dest="intro_duration", help="Intro duration (s)")
    parser.add_argument("--target-time", type=int, dest="target_time", help="Manual boundary time (s)")
    parser.add_argument("--time-margin", type=int, dest="time_margin", help="Search margin (s)")
    parser.add_argument("--no-auto-target", action="store_true", dest="no_auto_target",
                        help="Disable runtime-derived boundary")
    parser.add_argument("--detection-method", type=str, dest="detection_method",
                        help="Detection method name")
    parser.add_argument("--on-failure", type=str, dest="on_failure",
                        choices=["copy", "midpoint", "skip"], help="Behavior when no boundary is found")
    args = parser.parse_args()

    if args.cli:
        run_cli(args)
    else:
        run_gui()


if __name__ == "__main__":
    main()
