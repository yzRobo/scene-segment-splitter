"""
diagnostic_analyzer.py - Diagnostic tool to analyze specific timestamps in video files

This tool helps diagnose why certain black frames aren't being detected.
It extracts frames and analyzes their properties at specific timestamps.
"""

import subprocess
import os
import re
import sys
from pathlib import Path
import json
import tempfile
import shutil

class VideoAnalyzer:
    def __init__(self, video_path):
        self.video_path = video_path
        self.ffmpeg_path = self._get_ffmpeg_path()
        self.ffprobe_path = self._get_ffprobe_path()
        
    def _get_ffmpeg_path(self):
        """Get path to ffmpeg executable"""
        # Check local bin directory first
        bin_dir = os.path.join(os.path.dirname(__file__), 'bin')
        if os.path.exists(os.path.join(bin_dir, 'ffmpeg.exe')):
            return os.path.join(bin_dir, 'ffmpeg.exe')
        elif os.path.exists(os.path.join(bin_dir, 'ffmpeg')):
            return os.path.join(bin_dir, 'ffmpeg')
        
        # Try system PATH
        ffmpeg_path = shutil.which('ffmpeg')
        if ffmpeg_path:
            return ffmpeg_path
            
        raise FileNotFoundError("FFmpeg not found!")
    
    def _get_ffprobe_path(self):
        """Get path to ffprobe executable"""
        # Similar to ffmpeg
        bin_dir = os.path.join(os.path.dirname(__file__), 'bin')
        if os.path.exists(os.path.join(bin_dir, 'ffprobe.exe')):
            return os.path.join(bin_dir, 'ffprobe.exe')
        elif os.path.exists(os.path.join(bin_dir, 'ffprobe')):
            return os.path.join(bin_dir, 'ffprobe')
        
        ffprobe_path = shutil.which('ffprobe')
        if ffprobe_path:
            return ffprobe_path
            
        raise FileNotFoundError("FFprobe not found!")
    
    def analyze_timestamp(self, timestamp_seconds, duration=5):
        """Analyze video around a specific timestamp"""
        print(f"\n{'='*60}")
        print(f"Analyzing video around {self._seconds_to_time(timestamp_seconds)}")
        print(f"{'='*60}\n")
        
        # 1. Extract frames around timestamp
        print("1. Extracting frames...")
        self.extract_frames(timestamp_seconds, duration)
        
        # 2. Run multiple detection methods
        print("\n2. Running detection methods...")
        self.run_blackdetect(timestamp_seconds, duration)
        self.run_histogram_analysis(timestamp_seconds, duration)
        self.analyze_frame_properties(timestamp_seconds)
        
        # 3. Check for encoding issues
        print("\n3. Checking for encoding anomalies...")
        self.check_keyframes(timestamp_seconds)
        
    def _seconds_to_time(self, seconds):
        """Convert seconds to HH:MM:SS.mmm format"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:06.3f}"
    
    def extract_frames(self, timestamp, duration=5):
        """Extract frames as images for visual inspection"""
        start = max(0, timestamp - duration/2)
        
        # Create output directory
        output_dir = f"frames_analysis_{int(timestamp)}"
        os.makedirs(output_dir, exist_ok=True)
        
        # Extract 1 frame per second
        cmd = [
            self.ffmpeg_path,
            "-ss", str(start),
            "-i", self.video_path,
            "-t", str(duration),
            "-vf", "fps=2,showinfo",  # 2 fps for more detail
            "-frame_pts", "1",
            os.path.join(output_dir, "frame_%04d.png")
        ]
        
        print(f"Extracting frames to {output_dir}/")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Also extract the exact frame at timestamp
        exact_cmd = [
            self.ffmpeg_path,
            "-ss", str(timestamp),
            "-i", self.video_path,
            "-vframes", "1",
            os.path.join(output_dir, f"exact_frame_at_{int(timestamp)}.png")
        ]
        subprocess.run(exact_cmd, capture_output=True)
        
        print(f"Frames extracted. Check {output_dir}/ directory.")
        
    def run_blackdetect(self, timestamp, duration=5):
        """Run blackdetect around timestamp"""
        start = max(0, timestamp - duration/2)
        
        print(f"\nBlackdetect analysis ({self._seconds_to_time(start)} to {self._seconds_to_time(start + duration)}):")
        
        # Try different threshold values
        thresholds = [
            ("Standard", "d=0.2:pix_th=0.15:pic_th=0.95"),
            ("Lenient", "d=0.1:pix_th=0.25:pic_th=0.90"),
            ("Very Lenient", "d=0.05:pix_th=0.35:pic_th=0.80"),
            ("Ultra Lenient", "d=0.01:pix_th=0.50:pic_th=0.50")
        ]
        
        for name, params in thresholds:
            cmd = [
                self.ffmpeg_path,
                "-ss", str(start),
                "-t", str(duration),
                "-i", self.video_path,
                "-vf", f"blackdetect={params}",
                "-f", "null",
                "-"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            black_found = False
            for line in result.stderr.split('\n'):
                if "black_start" in line:
                    black_found = True
                    print(f"  {name}: {line.strip()}")
            
            if not black_found:
                print(f"  {name}: No black frames detected")
                
    def run_histogram_analysis(self, timestamp, duration=5):
        """Analyze luminance values frame by frame"""
        start = max(0, timestamp - duration/2)
        
        print(f"\nHistogram/Luminance analysis:")
        
        cmd = [
            self.ffmpeg_path,
            "-ss", str(start),
            "-t", str(duration),
            "-i", self.video_path,
            "-vf", "fps=10,signalstats,metadata=print",
            "-f", "null",
            "-"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        # metadata=print emits, per frame:
        #   pts_time:<seconds>
        #   lavfi.signalstats.YAVG=<float>  (and YMIN/YMAX)
        cur_time = start
        yavg = ymin = ymax = None
        for line in result.stderr.split('\n'):
            tmatch = re.search(r'pts_time:(\d+\.?\d*)', line)
            if tmatch:
                cur_time = float(tmatch.group(1))
                yavg = ymin = ymax = None
                continue
            m = re.search(r'lavfi\.signalstats\.YAVG=(\d+\.?\d*)', line)
            if m:
                yavg = float(m.group(1))
            m = re.search(r'lavfi\.signalstats\.YMIN=(\d+\.?\d*)', line)
            if m:
                ymin = float(m.group(1))
            m = re.search(r'lavfi\.signalstats\.YMAX=(\d+\.?\d*)', line)
            if m:
                ymax = float(m.group(1))
                if yavg is not None:
                    if abs(cur_time - timestamp) < 0.5:
                        print(f"  >>> {self._seconds_to_time(cur_time)}: Y-Avg={yavg:.1f}, "
                              f"Y-Min={ymin}, Y-Max={ymax} <<<")
                    elif yavg < 20:
                        print(f"  {self._seconds_to_time(cur_time)}: Y-Avg={yavg:.1f}, "
                              f"Y-Min={ymin}, Y-Max={ymax}")
                    
    def analyze_frame_properties(self, timestamp):
        """Get detailed properties of specific frame"""
        print(f"\nFrame properties at {self._seconds_to_time(timestamp)}:")
        
        cmd = [
            self.ffprobe_path,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_frames",
            "-read_intervals", f"{timestamp}%+#1",
            "-print_format", "json",
            self.video_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        try:
            data = json.loads(result.stdout)
            if data.get('frames'):
                frame = data['frames'][0]
                print(f"  Frame type: {frame.get('pict_type', 'Unknown')}")
                print(f"  Key frame: {frame.get('key_frame', 'Unknown')}")
                print(f"  PTS time: {frame.get('pts_time', 'Unknown')}")
                print(f"  Size: {frame.get('width', 'Unknown')}x{frame.get('height', 'Unknown')}")
        except:
            print("  Could not parse frame data")
            
    def check_keyframes(self, timestamp):
        """Check keyframe distribution around timestamp"""
        print(f"\nKeyframes around {self._seconds_to_time(timestamp)}:")
        
        start = max(0, timestamp - 5)
        end = timestamp + 5
        
        cmd = [
            self.ffprobe_path,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_frames",
            "-show_entries", "frame=key_frame,pts_time",
            "-read_intervals", f"{start}%{end}",
            "-print_format", "csv=p=0",
            self.video_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        keyframe_times = []
        for line in result.stdout.split('\n'):
            if line.strip():
                parts = line.split(',')
                if len(parts) >= 2 and parts[0] == '1':  # key_frame=1
                    try:
                        time = float(parts[1])
                        keyframe_times.append(time)
                        if abs(time - timestamp) < 2:
                            print(f"  Keyframe at {self._seconds_to_time(time)}")
                    except:
                        continue
                        
        # Check distance to nearest keyframe
        if keyframe_times:
            nearest = min(keyframe_times, key=lambda x: abs(x - timestamp))
            distance = abs(nearest - timestamp)
            print(f"  Nearest keyframe: {distance:.3f} seconds away")

def main():
    import re
    
    if len(sys.argv) < 2:
        print("Usage: python diagnostic_analyzer.py <video_file> [timestamp_in_seconds]")
        print("Example: python diagnostic_analyzer.py video.mp4 686")
        sys.exit(1)
    
    video_file = sys.argv[1]
    
    if not os.path.exists(video_file):
        print(f"Error: Video file '{video_file}' not found!")
        sys.exit(1)
    
    # Default to 686 seconds (11:26) if not specified
    timestamp = float(sys.argv[2]) if len(sys.argv) > 2 else 686
    
    analyzer = VideoAnalyzer(video_file)
    analyzer.analyze_timestamp(timestamp)
    
    print("\n" + "="*60)
    print("Analysis complete!")
    print("Check the frames_analysis_* directory for extracted frames.")
    print("="*60)

if __name__ == "__main__":
    main()