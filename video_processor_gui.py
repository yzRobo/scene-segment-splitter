"""
video_processor_gui.py - Extended Video Processor for GUI Integration

This module extends the original VideoProcessor class with GUI-specific features:
- Progress callbacks for real-time status updates
- Cancellation support for stopping mid-process
- Dynamic configuration from GUI parameters
- Enhanced logging with progress percentages

This should be imported by the GUI application instead of the original processor
when running in GUI mode.

Note: This inherits from the original VideoProcessor class in process_videos.py
"""

import os
import subprocess
import shutil
import csv
import re
import tempfile
import logging
import sys
import json
from datetime import datetime
from typing import List, Tuple, Optional, Dict
from pathlib import Path
from difflib import SequenceMatcher
import platform

# Import the base VideoProcessor class
from process_videos import VideoProcessor

class VideoProcessorGUI(VideoProcessor):
    """Extended VideoProcessor class with GUI-friendly features"""
    
    def __init__(self, input_folder: str, output_folder: str, config: dict = None):
        """Initialize with optional configuration dictionary"""
        super().__init__(input_folder, output_folder)
        
        # Apply configuration if provided
        if config:
            self.apply_config(config)
            
        # Callback for progress updates
        self.progress_callback = None
        self.cancel_requested = False
        
    def apply_config(self, config: dict):
        """Apply configuration from GUI"""
        self.INTRO_DURATION = config.get('intro_duration', 47)
        self.target_time = config.get('target_time', 710)
        self.time_margin = config.get('time_margin', 60)
        self.black_duration = config.get('black_duration', 0.2)
        self.pixel_threshold = config.get('pixel_threshold', 0.15)
        self.picture_threshold = config.get('picture_threshold', 0.95)
        
        # Load custom episode list if specified
        if 'episode_csv' in config:
            self.episode_map = self._load_episode_list(config['episode_csv'])
            
    def set_progress_callback(self, callback):
        """Set callback function for progress updates"""
        self.progress_callback = callback
        
    def cancel_processing(self):
        """Request cancellation of processing"""
        self.cancel_requested = True
        
    def _update_progress(self, message: str, percentage: float = None):
        """Send progress update to GUI"""
        if self.progress_callback:
            self.progress_callback(message, percentage)
        logging.info(message)
        
    def detect_black_frames(self, video_path: str) -> List[Tuple[float, float]]:
        """Modified to use configurable parameters"""
        self._update_progress("Analyzing video for black frames...")
        
        cmd = [
            self.ffmpeg_path,
            "-i", str(Path(video_path).resolve()),
            "-vf", f"blackdetect=d={self.black_duration}:pix_th={self.pixel_threshold}:pic_th={self.picture_threshold}",
            "-an",
            "-f", "null",
            "-"
        ]

        try:
            self._update_progress("Running black frame detection...")
            result = subprocess.run(cmd, capture_output=True, text=True)
            self._update_progress("Processing detection results...")
            
            black_frames = []
            for line in result.stderr.split('\n'):
                if "black_start:" in line:
                    try:
                        start = float(line.split("black_start:")[1].split()[0])
                        end = float(line.split("black_end:")[1].split()[0])
                        duration = float(line.split("black_duration:")[1].split()[0])
                        
                        if 0.2 <= duration <= 4.0:
                            black_frames.append((start, end, duration))
                            self._update_progress(f"Found black frame: {self._seconds_to_time(start)} - {self._seconds_to_time(end)} "
                                       f"(duration: {duration:.2f}s)")
                    except Exception as e:
                        logging.error(f"Error parsing line: {e}")
                        continue

            self._update_progress(f"Found {len(black_frames)} potential transitions")
            
            # Use configurable target time and margin
            time_filtered = []
            for start, end, duration in black_frames:
                if abs(start - self.target_time) <= self.time_margin:
                    time_filtered.append((start, end, duration))
                    self._update_progress(f"Found transition near target time: {self._seconds_to_time(start)} - "
                               f"{self._seconds_to_time(end)} (duration: {duration:.2f}s)")

            if time_filtered:
                self._update_progress(f"Found {len(time_filtered)} transitions near target time")
                
                def score_transition(transition):
                    start, end, duration = transition
                    time_score = abs(start - self.target_time) / self.time_margin
                    if 0.5 <= duration <= 2.0:
                        duration_score = 0
                    else:
                        duration_score = min(abs(duration - 0.5), abs(duration - 2.0))
                    
                    isolation_score = 0
                    for other_start, _, _ in black_frames:
                        if other_start != start:
                            distance = abs(start - other_start)
                            if distance < 5:
                                isolation_score += 1
                    
                    total_score = time_score + duration_score + (isolation_score * 0.5)
                    
                    return total_score
                
                best_transition = min(time_filtered, key=score_transition)
                self._update_progress(f"Selected transition at {self._seconds_to_time(best_transition[0])} "
                           f"(duration: {best_transition[2]:.2f}s)")
                
                return [(best_transition[0], best_transition[1])]
            
            return []

        except subprocess.CalledProcessError as e:
            logging.error(f"FFmpeg error: {e}")
            return []
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            return []
            
    def process_videos(self) -> None:
        """Modified to support progress updates and cancellation"""
        videos_found = False
        video_files = [f for f in os.listdir(self.input_folder) 
                      if f.lower().endswith(self.SUPPORTED_FORMATS)]
        
        total_videos = len(video_files)
        
        for index, file in enumerate(video_files):
            if self.cancel_requested:
                self._update_progress("Processing cancelled by user")
                break
                
            videos_found = True
            video_path = os.path.join(self.input_folder, file)
            
            progress_percentage = (index / total_videos) * 100
            self._update_progress(f"Processing {index + 1}/{total_videos}: {file}", progress_percentage)
            
            # Create a new temporary folder for each video file
            self.temp_folder = tempfile.mkdtemp()
            logging.info(f"Created temporary folder: {self.temp_folder}")

            # Convert to MKV if not already in MKV format
            if not file.lower().endswith('.mkv'):
                mkv_video_path = os.path.join(self.temp_folder, os.path.splitext(file)[0] + '.mkv')
                if not self.convert_to_mkv(video_path, mkv_video_path):
                    continue
                video_path = mkv_video_path
                self._update_progress(f"Converted {file} to MKV format for processing.")

            # Get show info and episode names
            show_name, season, episode, _ = self._get_episode_info(file)
            if not all([show_name, season, episode]):
                logging.error(f"Could not parse show information from filename: {file}")
                continue

            first_episode, second_episode = self._get_episode_names(file, show_name)
            
            # Check if this is a single-episode file
            if second_episode is None:
                episode_info = self._find_matching_episode(first_episode)
                if episode_info:
                    output_name = f"{show_name} - S{season:02d}E{episode:02d} - {episode_info['full_name']}{os.path.splitext(file)[1]}"
                    output_file = os.path.join(self.output_folder, self._sanitize_filename(output_name))
                    self._update_progress(f"Single episode file detected: {first_episode}")
                    self._update_progress(f"Copying directly to output: {output_name}")
                    shutil.copy2(video_path, output_file)
                
                # Clean up temp folder and continue to next file
                if os.path.exists(self.temp_folder):
                    shutil.rmtree(self.temp_folder)
                continue
                
            # For two-segment episodes, proceed with normal processing
            duration = self.get_video_duration(video_path)
            if duration:
                self._update_progress(f"Video duration: {duration:.2f} seconds ({duration/60:.2f} minutes)")
                
                transitions = self.detect_black_frames(video_path)
                if transitions:
                    episode1_start = "00:00:00.000"
                    episode1_end = self._seconds_to_time(transitions[0][0])
                    episode2_start = self._seconds_to_time(transitions[0][0])
                    episode2_end = self._seconds_to_time(duration)
                    
                    boundaries = [(episode1_start, episode1_end), (episode2_start, episode2_end)]
                    
                    ep1_length = transitions[0][0]
                    ep2_length = duration - transitions[0][1]
                    self._update_progress(f"Episode 1: {episode1_start} to {episode1_end} ({ep1_length/60:.2f} minutes)")
                    self._update_progress(f"Episode 2: {episode2_start} to {episode2_end} ({ep2_length/60:.2f} minutes)")
                    
                    self._update_progress(f"Splitting video...")
                    self.split_video(video_path, boundaries)
                    self._update_progress(f"Video splitting completed.")
                else:
                    self._update_progress("No valid transitions found")
            else:
                self._update_progress("Could not determine video duration")
            
            # Clean up the temporary folder after processing each video
            logging.info(f"Cleaning up temporary folder: {self.temp_folder}")
            if os.path.exists(self.temp_folder):
                shutil.rmtree(self.temp_folder)
        
        if not videos_found:
            self._update_progress(f"No supported video files found in {self.input_folder}")
            self._update_progress(f"Supported formats: {', '.join(self.SUPPORTED_FORMATS)}")
        else:
            self._update_progress("All videos processed!", 100)