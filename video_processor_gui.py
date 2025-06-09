"""
video_processor_gui.py - Extended Video Processor for GUI Integration

This module extends the original VideoProcessor class with GUI-specific features:
- Progress callbacks for real-time status updates
- Cancellation support for stopping mid-process
- Dynamic configuration from GUI parameters
- Enhanced logging with progress percentages
"""

import os
import subprocess
import shutil
import csv
import re
import tempfile
import logging
from datetime import datetime
from typing import List, Tuple, Optional, Dict
from pathlib import Path

from process_videos import VideoProcessor

class VideoProcessorGUI(VideoProcessor):
    """Extended VideoProcessor class with GUI-friendly features"""
    
    def __init__(self, input_folder: str, output_folder: str, config: dict = None):
        super().__init__(input_folder, output_folder)
        self.config = config or {}
        self.apply_config(self.config)
        self.progress_callback = None
        self.cancel_requested = False
        
    def apply_config(self, config: dict):
        self.INTRO_DURATION = config.get('intro_duration', 47)
        self.target_time = config.get('target_time', 710)
        self.time_margin = config.get('time_margin', 60)
        self.black_duration = config.get('black_duration', "0.2")
        self.pixel_threshold = config.get('pixel_threshold', "0.15")
        self.picture_threshold = config.get('picture_threshold', "0.95")
        self.transition_selection = config.get('transition_selection', "Select Latest Transition")
        self.split_point = config.get('split_point', "At Start of Fade")

        episode_csv_path = config.get('episode_csv')
        if episode_csv_path and os.path.exists(episode_csv_path):
            self.episode_map = self._load_episode_list(episode_csv_path)
            
    def set_progress_callback(self, callback): self.progress_callback = callback
    def cancel_processing(self): self.cancel_requested = True; self._update_progress("Cancellation requested...")
        
    def _update_progress(self, message: str, percentage: float = None):
        if message: logging.info(message)
        if self.progress_callback and percentage is not None:
            self.progress_callback(None, percentage)
        
    def detect_black_frames(self, video_path: str) -> List[Tuple[float, float, float]]:
        self._update_progress("Analyzing video for black frames...")
        cmd = [self.ffmpeg_path, "-i", str(Path(video_path).resolve()), "-vf", f"blackdetect=d={self.black_duration}:pix_th={self.pixel_threshold}:pic_th={self.picture_threshold}", "-an", "-f", "null", "-"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            black_frames = []
            for line in result.stderr.split('\n'):
                if "black_start:" in line:
                    try:
                        start = float(line.split("black_start:")[1].split()[0])
                        end = float(line.split("black_end:")[1].split()[0])
                        duration = float(line.split("black_duration:")[1].split()[0])
                        if 0.1 <= duration <= 5.0: black_frames.append((start, end, duration))
                    except (IndexError, ValueError): continue
            
            time_filtered = [bf for bf in black_frames if abs(bf[0] - self.target_time) <= self.time_margin]
            self._update_progress(f"Found {len(time_filtered)} transitions in the target window.")
            for tf in time_filtered: self._update_progress(f"  - Transition candidate at: {self._seconds_to_time(tf[0])}")

            if time_filtered:
                if self.transition_selection == "Select Latest Transition":
                    time_filtered.sort(key=lambda x: x[0], reverse=True)
                    self._update_progress("Selecting LATEST transition from window.")
                else: # "Select Earliest Transition"
                    time_filtered.sort(key=lambda x: x[0])
                    self._update_progress("Selecting EARLIEST transition from window.")
                
                best_transition = time_filtered[0]
                self._update_progress(f"Selected transition starts at {self._seconds_to_time(best_transition[0])}")
                return [best_transition]
            
            self._update_progress("No suitable transitions found.")
            return []
        except subprocess.CalledProcessError as e:
            self._update_progress(f"FFmpeg error: {e.stderr}"); return []
        except Exception as e:
            self._update_progress(f"Error during detection: {e}"); return []
            
    def process_videos(self) -> None:
        video_files = [f for f in os.listdir(self.input_folder) if f.lower().endswith(self.SUPPORTED_FORMATS)]
        total_videos = len(video_files)
        if not total_videos: self._update_progress("No supported video files found."); return

        for index, file in enumerate(video_files):
            if self.cancel_requested: break
            self._update_progress(f"\n--- Processing {index + 1}/{total_videos}: {file} ---", (index/total_videos)*100)
            
            self.temp_folder = tempfile.mkdtemp()
            video_path = os.path.join(self.input_folder, file)
            if not file.lower().endswith('.mkv'):
                mkv_path = os.path.join(self.temp_folder, os.path.splitext(file)[0] + '.mkv')
                if self.convert_to_mkv(video_path, mkv_path): video_path = mkv_path
                else: shutil.rmtree(self.temp_folder, ignore_errors=True); continue

            show_name, season, episode, _ = self._get_episode_info(file)
            if not all([show_name, season, episode]):
                self._update_progress(f"ERROR: Could not parse show info from filename."); shutil.rmtree(self.temp_folder, ignore_errors=True); continue
            
            first_episode, second_episode = self._get_episode_names(file, show_name)
            if not second_episode:
                info = self._find_matching_episode(first_episode)
                if info:
                    output_name = f"{show_name} - S{season:02d}E{info['episode']:02d} - {info['full_name']}{os.path.splitext(file)[1]}"
                    shutil.copy2(video_path, os.path.join(self.output_folder, self._sanitize_filename(output_name)))
                    self._update_progress(f"Single episode file. Copied to: {output_name}")
                shutil.rmtree(self.temp_folder, ignore_errors=True); continue

            duration = self.get_video_duration(video_path)
            if not duration: shutil.rmtree(self.temp_folder, ignore_errors=True); continue
            self._update_progress(f"Video duration: {self._seconds_to_time(duration)}")
            
            transitions = self.detect_black_frames(video_path)
            if transitions:
                transition_start, transition_end, _ = transitions[0]
                
                # === CORRECTED SPLIT LOGIC ===
                if self.split_point == "After Fade":
                    self._update_progress("Using 'After Fade' (Clean Cut) split logic.")
                    ep1_end_time = self._seconds_to_time(transition_start)
                    ep2_start_time = self._seconds_to_time(transition_end)
                else: # "At Start of Fade"
                    self._update_progress("Using 'At Start of Fade' (Legacy) split logic.")
                    ep1_end_time = self._seconds_to_time(transition_start)
                    ep2_start_time = self._seconds_to_time(transition_start)

                ep2_end_time = self._seconds_to_time(duration)

                boundaries = [("00:00:00.000", ep1_end_time), (ep2_start_time, ep2_end_time)]
                self._update_progress(f"Episode 1: 00:00:00.000 to {ep1_end_time}"); self._update_progress(f"Episode 2: {ep2_start_time} to {ep2_end_time}")
                self.split_video(video_path, boundaries)
            
            shutil.rmtree(self.temp_folder, ignore_errors=True)
        
        status = "Processing stopped." if self.cancel_requested else "All videos processed!"
        self._update_progress(status, 100)