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

def setup_logging():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"video_processing_{timestamp}.log"
    
    # Configure logging to write to both file and console
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(message)s',
        handlers=[
            logging.FileHandler(log_filename, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return log_filename

class VideoProcessor:
    SUPPORTED_FORMATS = ('.mkv', '.mp4')
    INTRO_DURATION = 47  # Duration of the intro in seconds (adjust as needed)

    def __init__(self, input_folder: str, output_folder: str):
        """Initialize the video processor with input and output folders"""
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.episode_map = self._load_episode_list("episode_list.csv")
        os.makedirs(output_folder, exist_ok=True)
        self.ffmpeg_path = self._get_ffmpeg_path()
        self.ffprobe_path = self._get_ffprobe_path()
        self.temp_folder = tempfile.mkdtemp()  # Create a temporary directory

    def _load_episode_list(self, episode_list_path: str) -> Dict[str, str]:
        """Load episode list from CSV and create a mapping of episode names to episode codes"""
        episode_map = {}
        try:
            with open(episode_list_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Create normalized version of episode name for matching
                    normalized_name = self._normalize_title(row['EpisodeName'])
                    episode_map[normalized_name] = {
                        'season': int(row['SeasonNumber']),
                        'episode': int(row['EpisodeNumber']),
                        'full_name': row['EpisodeName']
                    }
        except Exception as e:
            logging.error(f"Error loading episode list: {e}")
            return {}
        return episode_map

    def _normalize_title(self, title: str) -> str:
        """Normalize title for matching by handling punctuation carefully"""
        # Step 1: Preserve specific patterns we want to keep
        # Common title abbreviations
        preserved_patterns = {
            r'Mr\.': 'Mr',
            r'Mrs\.': 'Mrs',
            r'Ms\.': 'Ms',
            r'Dr\.': 'Dr',
            r'Jr\.': 'Jr',
            r'Sr\.': 'Sr',
            r'St\.': 'St',
            r'vs\.': 'vs',
            # Handle ellipsis and other common punctuation patterns
            r'\.\.\.': ' ',  # Replace ellipsis with space
            r'\s*&\s*': ' and ',  # Replace & with 'and'
            r'\s*\+\s*': ' and ',  # Replace + with 'and'
            # Keep hyphenated words together
            r'(\w)-(\w)': r'\1\2'  # Remove hyphens between words but keep words together
        }
        
        working_title = title
        for pattern, replacement in preserved_patterns.items():
            working_title = re.sub(pattern, replacement, working_title)
        
        # Convert to lowercase after preserving patterns
        working_title = working_title.lower()
        
        # Remove any remaining punctuation
        working_title = re.sub(r'[^\w\s]', '', working_title)
        
        # Clean up whitespace
        working_title = re.sub(r'\s+', ' ', working_title).strip()
        
        return working_title

    def _sanitize_filename(self, filename: str) -> str:
        """Remove or replace invalid filename characters"""
        # Handle special cases first
        filename = filename.replace('?', '')
        # Replace other invalid characters with underscore
        return re.sub(r'[<>:"/\\|*]', '_', filename)
    
    def _get_episode_info(self, filename: str) -> Tuple[str, str, int, int]:
        """Extract show name, season and episode info from filename"""
        # Expected format: "Show Name - SXXEXX - Episode"
        pattern = r'^(.+?)\s*-\s*S(\d+)E(\d+)(?:-\d+)?\s*-\s*(.+)$'
        match = re.match(pattern, os.path.splitext(filename)[0])
        if match:
            show_name = match.group(1).strip()
            season = int(match.group(2))
            episode = int(match.group(3))
            remainder = match.group(4).strip()
            return show_name, season, episode, remainder
        return None, None, None, None

    def _get_episode_names(self, filename: str, show_name: str) -> Tuple[str, str]:
        """Extract the episode names from the filename"""
        # Remove quality indicators and file extension
        clean_name = re.sub(r'WEBDL-\d+p|DVD|\.mkv|\.mp4', '', filename)
        # Remove season/episode numbers and show name
        show_name_pattern = re.escape(show_name)
        clean_name = re.sub(rf'{show_name_pattern}\s*-\s*S\d+E\d+(-\d+)?\s*-\s*', '', clean_name)
        
        # Split by '+' and clean up
        parts = [part.strip() for part in clean_name.split('+')]
        if len(parts) == 2:
            return parts[0], parts[1]
        else:
            return clean_name.strip(), None

    def _find_matching_episode(self, episode_name: str) -> Optional[Dict]:
        """Find matching episode in the episode map"""
        normalized_name = self._normalize_title(episode_name)
        logging.debug(f"\nDebug: Looking for match for '{episode_name}'")
        logging.debug(f"Debug: Normalized name: '{normalized_name}'")
        
        # Remove 'DVD' or quality indicators from search
        search_name = re.sub(r'\s*(DVD|WEBDL-\d+p)$', '', normalized_name)
        logging.debug(f"Debug: Search name: '{search_name}'")
        
        # Direct match
        if search_name in self.episode_map:
            logging.debug(f"Debug: Found direct match")
            return self.episode_map[search_name]
        
        # Fuzzy match if needed
        try:
            best_match = None
            best_ratio = 0
            
            logging.debug("\nDebug: Attempting fuzzy matches:")
            matches = []
            for name, info in self.episode_map.items():
                ratio = SequenceMatcher(None, search_name, name).ratio()
                matches.append((name, ratio, info))
            
            # Sort by ratio and print top 3
            matches.sort(key=lambda x: x[1], reverse=True)
            for name, ratio, info in matches[:3]:
                logging.debug(f"Debug: '{name}' - confidence: {ratio:.2f}")
                if ratio > 0.75 and ratio > best_ratio:  # Lowered threshold from 0.8 to 0.75
                    best_ratio = ratio
                    best_match = info
            
            if best_match:
                logging.debug(f"Debug: Selected match: '{best_match['full_name']}' with confidence {best_ratio:.2f}")
            else:
                logging.debug(f"Debug: No match found above 0.75 confidence threshold")
                
            return best_match
        except Exception as e:
            logging.error(f"Error during fuzzy matching: {e}")
            return None

    def _get_next_episode(self, current_episode: str) -> Optional[Dict]:
        current_info = self._find_matching_episode(current_episode)
        if current_info:
            next_episode_num = current_info['episode'] + 1
            # Look for episode with this number in the same season
            for name, info in self.episode_map.items():
                if info['season'] == current_info['season'] and info['episode'] == next_episode_num:
                    return info
        return None

    def _get_ffmpeg_path(self) -> str:
        """Get path to ffmpeg executable"""
        ffmpeg_path = shutil.which('ffmpeg')
        if ffmpeg_path:
            return ffmpeg_path
        
        common_paths = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe"
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                return path
        
        raise FileNotFoundError("FFmpeg not found. Please install FFmpeg and add it to PATH.")

    def _get_ffprobe_path(self) -> str:
        """Get path to ffprobe executable"""
        ffprobe_path = shutil.which('ffprobe')
        if ffprobe_path:
            return ffprobe_path
            
        common_paths = [
            os.path.join(os.path.dirname(self.ffmpeg_path), 'ffprobe.exe'),
            r"C:\ffmpeg\bin\ffprobe.exe",
            r"C:\Program Files\ffmpeg\bin\ffprobe.exe"
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                return path
                
        raise FileNotFoundError("ffprobe not found. Please install FFmpeg with ffprobe.")

    def _time_to_seconds(self, time_str: str) -> float:
        """Convert timestamp string (HH:MM:SS.mmm) to seconds"""
        h, m, s = time_str.split(':')
        return float(h) * 3600 + float(m) * 60 + float(s)

    def _seconds_to_time(self, seconds: float) -> str:
        """Convert seconds to timestamp string (HH:MM:SS.mmm)"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:06.3f}"

    def get_video_duration(self, video_path: str) -> Optional[float]:
        """Get video duration using ffprobe"""
        try:
            cmd = [
                self.ffprobe_path,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(Path(video_path).resolve())
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logging.error(f"FFprobe error: {result.stderr}")
                return None
                
            data = json.loads(result.stdout)
            return float(data['format']['duration'])
            
        except Exception as e:
            logging.error(f"Error getting video duration: {e}")
            return None

    def _create_concat_file(self, intro_path: str, episode_path: str) -> str:
        """Create a concat file for FFmpeg"""
        concat_file = os.path.join(self.temp_folder, "concat.txt")
        with open(concat_file, 'w', encoding='utf-8') as f:
            f.write(f"file '{intro_path.replace(os.sep, '/')}'\n")
            f.write(f"file '{episode_path.replace(os.sep, '/')}'\n")
        return concat_file
    
    def detect_black_frames(self, video_path: str) -> List[Tuple[float, float]]:
        """Use FFmpeg to detect black frames/scenes"""
        logging.info("\nAnalyzing video for black frames...")
        
        cmd = [
            self.ffmpeg_path,
            "-i", str(Path(video_path).resolve()),
            "-vf", "blackdetect=d=0.2:pix_th=0.15:pic_th=0.95",
            "-an",
            "-f", "null",
            "-"
        ]

        try:
            logging.info("Running black frame detection...")
            result = subprocess.run(cmd, capture_output=True, text=True)
            logging.info("\nProcessing detection results...")
            
            black_frames = []
            for line in result.stderr.split('\n'):
                if "black_start:" in line:
                    logging.info(f"Found line: {line}")
                    try:
                        start = float(line.split("black_start:")[1].split()[0])
                        end = float(line.split("black_end:")[1].split()[0])
                        duration = float(line.split("black_duration:")[1].split()[0])
                        
                        if 0.2 <= duration <= 4.0:
                            black_frames.append((start, end, duration))
                            logging.info(f"Found black frame: {self._seconds_to_time(start)} - {self._seconds_to_time(end)} "
                                       f"(duration: {duration:.2f}s)")
                    except Exception as e:
                        logging.error(f"Error parsing line: {e}")
                        continue

            logging.info(f"\nFound {len(black_frames)} potential transitions")
            
            target_time = 710  # 11:50 in seconds
            margin = 60  # ±60 seconds
            
            time_filtered = []
            for start, end, duration in black_frames:
                if abs(start - target_time) <= margin:
                    time_filtered.append((start, end, duration))
                    logging.info(f"Found transition near target time: {self._seconds_to_time(start)} - "
                               f"{self._seconds_to_time(end)} (duration: {duration:.2f}s)")
            
            if time_filtered:
                logging.info(f"Found {len(time_filtered)} transitions near target time")
                
                def score_transition(transition):
                    start, end, duration = transition
                    time_score = abs(start - target_time) / margin
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
                    logging.info(f"Transition at {self._seconds_to_time(start)} scored: {total_score:.2f}")
                    logging.info(f"  Time score: {time_score:.2f}")
                    logging.info(f"  Duration score: {duration_score:.2f}")
                    logging.info(f"  Isolation score: {isolation_score:.2f}")
                    
                    return total_score
                
                best_transition = min(time_filtered, key=score_transition)
                logging.info(f"\nSelected transition at {self._seconds_to_time(best_transition[0])} "
                           f"(duration: {best_transition[2]:.2f}s)")
                
                return [(best_transition[0], best_transition[1])]
            
            return []

        except subprocess.CalledProcessError as e:
            logging.error(f"FFmpeg error: {e}")
            if e.stderr:
                logging.error("Error output:", e.stderr)
            return []
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            return []

    def split_video(self, video_path: str, segments: List[Tuple[str, str]]) -> None:
        video_name = os.path.splitext(os.path.basename(video_path))[0]
        input_ext = os.path.splitext(video_path)[1].lower()
        
        # Extract show info and episode names first
        show_name, season, base_episode, _ = self._get_episode_info(video_name)
        if not all([show_name, season, base_episode]):
            logging.error(f"Could not parse show information from filename: {video_name}")
            return
        
        first_episode, second_episode = self._get_episode_names(video_name, show_name)
        
        # Look up both episodes in CSV before starting
        first_episode_info = self._find_matching_episode(first_episode)
        second_episode_info = self._find_matching_episode(second_episode) if second_episode else None
        
        # Extract intro (re-encoded)
        intro_file = os.path.join(self.temp_folder, f"intro{input_ext}")
        intro_cmd = [
            self.ffmpeg_path,
            "-i", str(Path(video_path).resolve()),
            "-t", str(self.INTRO_DURATION - 0.5),  # Slightly reduce duration
            "-c:v", "libx264",
            "-c:a", "aac",
            "-y",
            str(Path(intro_file).resolve())
        ]
        
        try:
            logging.info("\nExtracting intro segment...")
            subprocess.run(intro_cmd, capture_output=True, text=True, check=True)
        except Exception as e:
            logging.error(f"Error extracting intro: {e}")
            return

        for i, (start, end) in enumerate(segments, 1):
            if i == 1:
                episode_info = first_episode_info
                episode_name = first_episode
            else:
                episode_info = second_episode_info
                episode_name = second_episode
                
            if episode_info:
                output_name = f"{show_name} - S{season:02d}E{episode_info['episode']:02d} - {episode_info['full_name']}{input_ext}"
            else:
                # Fallback if episode not found in CSV
                output_name = f"{show_name} - S{season:02d}E{base_episode + i:02d} - {episode_name}{input_ext}"
                
            output_file = os.path.join(self.output_folder, self._sanitize_filename(output_name))
            
            if i == 1:
                # Process first episode
                extract_cmd = [
                    self.ffmpeg_path,
                    "-i", str(Path(video_path).resolve()),
                    "-ss", start,
                    "-to", end,
                    "-c", "copy",
                    "-y",
                    str(Path(output_file).resolve())
                ]
                
                subprocess.run(extract_cmd, capture_output=True, text=True, check=True)
                logging.info(f"Successfully created episode {i}")
            else:
                # Process second episode with intro
                temp_episode = os.path.join(self.temp_folder, f"temp_episode{i}{input_ext}")
                extract_cmd = [
                    self.ffmpeg_path,
                    "-i", str(Path(video_path).resolve()),
                    "-ss", start,
                    "-to", end,
                    "-c:v", "libx264",
                    "-c:a", "aac",
                    "-y",
                    str(Path(temp_episode).resolve())
                ]
                
                subprocess.run(extract_cmd, capture_output=True, text=True, check=True)
                
                # Concatenate with intro
                concat_file = self._create_concat_file(intro_file, temp_episode)
                concat_cmd = [
                    self.ffmpeg_path,
                    "-f", "concat",
                    "-safe", "0",
                    "-i", concat_file,
                    "-c:v", "libx264",
                    "-c:a", "aac",
                    "-y",
                    str(Path(output_file).resolve())
                ]
                
                subprocess.run(concat_cmd, capture_output=True, text=True, check=True)
            
                # Clean up temp files
                if os.path.exists(temp_episode):
                    os.remove(temp_episode)
                if os.path.exists(concat_file):
                    os.remove(concat_file)

        # Clean up intro file
        if os.path.exists(intro_file):
            os.remove(intro_file)
        
        # Try to remove temp directory if empty
        try:
            os.rmdir(self.temp_folder)
        except:
            pass

    def process_videos(self) -> None:
        """Process all videos in the input folder"""
        videos_found = False
        for file in os.listdir(self.input_folder):
            if file.lower().endswith(self.SUPPORTED_FORMATS):
                videos_found = True
                video_path = os.path.join(self.input_folder, file)
                logging.info(f"\nProcessing: {file}")
                
                # Create a new temporary folder for each video file
                self.temp_folder = tempfile.mkdtemp()
                logging.info(f"Created temporary folder: {self.temp_folder}")

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
                        logging.info(f"\nSingle episode file detected: {first_episode}")
                        logging.info(f"Copying directly to output: {output_name}")
                        shutil.copy2(video_path, output_file)
                    
                    # Clean up temp folder and continue to next file
                    if os.path.exists(self.temp_folder):
                        shutil.rmtree(self.temp_folder)
                    continue
                    
                # For two-segment episodes, proceed with normal processing
                duration = self.get_video_duration(video_path)
                if duration:
                    logging.info(f"Video duration: {duration:.2f} seconds ({duration/60:.2f} minutes)")
                    
                    transitions = self.detect_black_frames(video_path)
                    if transitions:
                        episode1_start = "00:00:00.000"
                        episode1_end = self._seconds_to_time(transitions[0][0])
                        episode2_start = self._seconds_to_time(transitions[0][1])
                        episode2_end = self._seconds_to_time(duration)
                        
                        boundaries = [(episode1_start, episode1_end), (episode2_start, episode2_end)]
                        
                        ep1_length = transitions[0][0]
                        ep2_length = duration - transitions[0][1]
                        logging.info(f"\nEpisode 1: {episode1_start} to {episode1_end} ({ep1_length/60:.2f} minutes)")
                        logging.info(f"Episode 2: {episode2_start} to {episode2_end} ({ep2_length/60:.2f} minutes)")
                        
                        logging.info(f"Splitting video...")
                        self.split_video(video_path, boundaries)
                        logging.info(f"Video splitting completed.")
                    else:
                        logging.info("No valid transitions found")
                else:
                    logging.info("Could not determine video duration")
                
                # Clean up the temporary folder after processing each video
                logging.info(f"Cleaning up temporary folder: {self.temp_folder}")
                if os.path.exists(self.temp_folder):
                    shutil.rmtree(self.temp_folder)
                else:
                    logging.info(f"Temporary folder {self.temp_folder} not found. Skipping cleanup.")
        
        if not videos_found:
            logging.info(f"\nNo supported video files found in {self.input_folder}")
            logging.info(f"Supported formats: {', '.join(self.SUPPORTED_FORMATS)}")

if __name__ == "__main__":
    log_file = setup_logging()
    logging.info(f"Starting video processing at {datetime.now()}")
    logging.info(f"Log file: {log_file}")
    processor = VideoProcessor("input_videos", "output_videos")
    processor.process_videos()
    logging.info(f"Processing completed at {datetime.now()}")