"""
gui.py - Scene Segment Splitter GUI Application

This is the main GUI interface for the Scene Segment Splitter.
It provides a user-friendly interface for:
- Selecting input/output folders and episode CSV files
- Configuring video processing parameters
- Real-time monitoring of processing progress
- Saving/loading configuration profiles

Usage: python gui.py
Or run through the launcher: python scene_splitter.py (GUI mode by default)
"""

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import queue
import os
import sys
from pathlib import Path
from datetime import datetime
import json
import tempfile
import re

# Import the existing video processor
from process_videos import VideoProcessor, setup_logging

class VideoSplitterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Scene Segment Splitter")
        self.root.geometry("900x700")
        
        # Initialize variables
        self.input_folder = tk.StringVar(value="input_videos")
        self.output_folder = tk.StringVar(value="output_videos")
        self.episode_csv = tk.StringVar(value="episode_list.csv")
        self.intro_duration = tk.IntVar(value=47)
        self.processing = False
        self.processor_thread = None
        self.log_queue = queue.Queue()
        
        # Create the GUI
        self.create_widgets()
        
        # Start log monitoring
        self.root.after(100, self.check_log_queue)
        
    def create_widgets(self):
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Main processing tab
        self.main_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.main_tab, text="Main")
        self.create_main_tab()
        
        # Configuration tab
        self.config_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.config_tab, text="Configuration")
        self.create_config_tab()
        
        # Episode Manager tab
        self.episode_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.episode_tab, text="Episode Manager")
        self.create_episode_tab()
        
        # Create status bar
        self.status_bar = ttk.Label(self.root, text="Ready", relief=tk.SUNKEN)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
    def create_main_tab(self):
        # Input/Output folder selection
        folder_frame = ttk.LabelFrame(self.main_tab, text="Folders", padding=10)
        folder_frame.pack(fill="x", padx=10, pady=5)
        
        # Input folder
        ttk.Label(folder_frame, text="Input Folder:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(folder_frame, textvariable=self.input_folder, width=50).grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(folder_frame, text="Browse", command=lambda: self.browse_folder(self.input_folder)).grid(row=0, column=2, padx=5, pady=5)
        
        # Output folder
        ttk.Label(folder_frame, text="Output Folder:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(folder_frame, textvariable=self.output_folder, width=50).grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(folder_frame, text="Browse", command=lambda: self.browse_folder(self.output_folder)).grid(row=1, column=2, padx=5, pady=5)
        
        # Episode CSV
        ttk.Label(folder_frame, text="Episode CSV:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(folder_frame, textvariable=self.episode_csv, width=50).grid(row=2, column=1, padx=5, pady=5)
        ttk.Button(folder_frame, text="Browse", command=self.browse_csv).grid(row=2, column=2, padx=5, pady=5)
        
        # Control buttons
        control_frame = ttk.Frame(self.main_tab)
        control_frame.pack(fill="x", padx=10, pady=10)
        
        self.process_button = ttk.Button(control_frame, text="Start Processing", command=self.start_processing, style="Accent.TButton")
        self.process_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(control_frame, text="Stop", command=self.stop_processing, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(control_frame, text="Clear Log", command=self.clear_log).pack(side=tk.RIGHT, padx=5)
        
        # Progress bar
        self.progress = ttk.Progressbar(self.main_tab, mode='indeterminate')
        self.progress.pack(fill="x", padx=10, pady=5)
        
        # Log viewer
        log_frame = ttk.LabelFrame(self.main_tab, text="Processing Log", padding=10)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=20, wrap=tk.WORD)
        self.log_text.pack(fill="both", expand=True)
        
    def create_config_tab(self):
        # Basic settings
        basic_frame = ttk.LabelFrame(self.config_tab, text="Basic Settings", padding=10)
        basic_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(basic_frame, text="Intro Duration (seconds):").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        intro_spinbox = ttk.Spinbox(basic_frame, from_=0, to=300, textvariable=self.intro_duration, width=10)
        intro_spinbox.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        # Black frame detection settings
        detection_frame = ttk.LabelFrame(self.config_tab, text="Black Frame Detection", padding=10)
        detection_frame.pack(fill="x", padx=10, pady=5)
        
        # Target time
        self.target_time = tk.IntVar(value=710)  # 11:50 in seconds
        ttk.Label(detection_frame, text="Target Transition Time (seconds):").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        ttk.Spinbox(detection_frame, from_=0, to=7200, textvariable=self.target_time, width=10).grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        # Time margin
        self.time_margin = tk.IntVar(value=60)
        ttk.Label(detection_frame, text="Time Margin (±seconds):").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        ttk.Spinbox(detection_frame, from_=10, to=300, textvariable=self.time_margin, width=10).grid(row=1, column=1, padx=5, pady=5, sticky="w")
        
        # Detection parameters
        self.black_duration = tk.StringVar(value="0.2")
        self.pixel_threshold = tk.StringVar(value="0.15")
        self.picture_threshold = tk.StringVar(value="0.95")
        
        ttk.Label(detection_frame, text="Black Duration:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(detection_frame, textvariable=self.black_duration, width=10).grid(row=2, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Label(detection_frame, text="Pixel Threshold:").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(detection_frame, textvariable=self.pixel_threshold, width=10).grid(row=3, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Label(detection_frame, text="Picture Threshold:").grid(row=4, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(detection_frame, textvariable=self.picture_threshold, width=10).grid(row=4, column=1, padx=5, pady=5, sticky="w")
        
        # Save/Load configuration
        config_control_frame = ttk.Frame(self.config_tab)
        config_control_frame.pack(fill="x", padx=10, pady=10)
        
        ttk.Button(config_control_frame, text="Save Configuration", command=self.save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(config_control_frame, text="Load Configuration", command=self.load_config).pack(side=tk.LEFT, padx=5)
        
    def browse_folder(self, var):
        folder = filedialog.askdirectory(initialdir=var.get())
        if folder:
            var.set(folder)
            
    def browse_csv(self):
        file = filedialog.askopenfilename(
            initialdir=os.path.dirname(self.episode_csv.get()),
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if file:
            self.episode_csv.set(file)
            
    def clear_log(self):
        self.log_text.delete(1.0, tk.END)
        
    def update_status(self, message):
        self.status_bar.config(text=message)
        
    def log_message(self, message):
        self.log_queue.put(message)
        
    def check_log_queue(self):
        try:
            while True:
                message = self.log_queue.get_nowait()
                self.log_text.insert(tk.END, message + "\n")
                self.log_text.see(tk.END)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.check_log_queue)
            
    def start_processing(self):
        if self.processing:
            return
            
        # Validate inputs
        if not os.path.exists(self.input_folder.get()):
            tk.messagebox.showerror("Error", "Input folder does not exist!")
            return
            
        if not os.path.exists(self.episode_csv.get()):
            tk.messagebox.showerror("Error", "Episode CSV file does not exist!")
            return
            
        # Update UI
        self.processing = True
        self.process_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.progress.start(10)
        self.update_status("Processing...")
        
        # Start processing in a separate thread
        self.processor_thread = threading.Thread(target=self.run_processor)
        self.processor_thread.daemon = True
        self.processor_thread.start()
        
    def stop_processing(self):
        # TODO: Implement proper stopping mechanism
        self.processing = False
        self.update_status("Stopping...")
        
    def run_processor(self):
        try:
            # Redirect logging to our GUI
            import logging
            
            class GUILogHandler(logging.Handler):
                def __init__(self, gui):
                    super().__init__()
                    self.gui = gui
                    
                def emit(self, record):
                    msg = self.format(record)
                    self.gui.log_message(msg)
                    
            # Setup logging with our custom handler
            log_handler = GUILogHandler(self)
            log_handler.setFormatter(logging.Formatter('%(message)s'))
            
            logger = logging.getLogger()
            logger.handlers = []  # Clear existing handlers
            logger.addHandler(log_handler)
            logger.setLevel(logging.DEBUG)
            
            # Create processor with custom parameters
            processor = VideoProcessor(
                self.input_folder.get(),
                self.output_folder.get()
            )
            
            # Override settings with GUI values
            processor.INTRO_DURATION = self.intro_duration.get()
            processor.episode_map = processor._load_episode_list(self.episode_csv.get())
            
            # Process videos
            processor.process_videos()
            
            self.update_status("Processing completed!")
            
        except Exception as e:
            self.log_message(f"Error: {str(e)}")
            self.update_status("Processing failed!")
            
        finally:
            self.processing = False
            self.process_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.progress.stop()
            
    def save_config(self):
        config = {
            "input_folder": self.input_folder.get(),
            "output_folder": self.output_folder.get(),
            "episode_csv": self.episode_csv.get(),
            "intro_duration": self.intro_duration.get(),
            "target_time": self.target_time.get(),
            "time_margin": self.time_margin.get(),
            "black_duration": self.black_duration.get(),
            "pixel_threshold": self.pixel_threshold.get(),
            "picture_threshold": self.picture_threshold.get()
        }
        
        # Default to configs directory
        configs_dir = os.path.join(os.path.dirname(__file__), 'configs')
        os.makedirs(configs_dir, exist_ok=True)
        
        file = filedialog.asksaveasfilename(
            initialdir=configs_dir,
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if file:
            with open(file, 'w') as f:
                json.dump(config, f, indent=4)
            self.update_status(f"Configuration saved to {os.path.basename(file)}")
            
    def load_config(self):
        # Default to configs directory
        configs_dir = os.path.join(os.path.dirname(__file__), 'configs')
        os.makedirs(configs_dir, exist_ok=True)
        
        file = filedialog.askopenfilename(
            initialdir=configs_dir,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if file:
            try:
                with open(file, 'r') as f:
                    config = json.load(f)
                    
                # Update GUI with loaded values
                self.input_folder.set(config.get("input_folder", "input_videos"))
                self.output_folder.set(config.get("output_folder", "output_videos"))
                self.episode_csv.set(config.get("episode_csv", "episode_list.csv"))
                self.intro_duration.set(config.get("intro_duration", 47))
                self.target_time.set(config.get("target_time", 710))
                self.time_margin.set(config.get("time_margin", 60))
                self.black_duration.set(config.get("black_duration", "0.2"))
                self.pixel_threshold.set(config.get("pixel_threshold", "0.15"))
                self.picture_threshold.set(config.get("picture_threshold", "0.95"))
                
                self.update_status(f"Configuration loaded from {file}")
            except Exception as e:
                tk.messagebox.showerror("Error", f"Failed to load configuration: {str(e)}")
    
    def create_episode_tab(self):
        # Instructions
        instructions_frame = ttk.LabelFrame(self.episode_tab, text="Instructions", padding=10)
        instructions_frame.pack(fill="x", padx=10, pady=5)
        
        instructions_text = """Paste your episode list in one of these formats:
1. "S01E01 - Episode Title" or "1x01 - Episode Title"
2. "Season 1, Episode 1: Episode Title"
3. Simple numbered list: "1. Episode Title" (specify season)
4. Copy from Wikipedia, IMDB, TheTVDB, etc.

The tool will try to auto-detect the format and convert it to CSV."""
        
        ttk.Label(instructions_frame, text=instructions_text, wraplength=850).pack(pady=5)
        
        # Input section
        input_frame = ttk.LabelFrame(self.episode_tab, text="Paste Episode List", padding=10)
        input_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Show name input
        name_frame = ttk.Frame(input_frame)
        name_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(name_frame, text="Show Name (optional):").pack(side=tk.LEFT, padx=5)
        self.show_name_var = tk.StringVar()
        ttk.Entry(name_frame, textvariable=self.show_name_var, width=30).pack(side=tk.LEFT, padx=5)
        
        # Season override for simple lists
        ttk.Label(name_frame, text="Default Season:").pack(side=tk.LEFT, padx=(20, 5))
        self.default_season_var = tk.IntVar(value=1)
        ttk.Spinbox(name_frame, from_=1, to=20, textvariable=self.default_season_var, width=5).pack(side=tk.LEFT)
        
        # Text input area
        self.episode_input_text = scrolledtext.ScrolledText(input_frame, height=10, wrap=tk.WORD)
        self.episode_input_text.pack(fill="both", expand=True, pady=5)
        
        # Control buttons
        control_frame = ttk.Frame(input_frame)
        control_frame.pack(fill="x", pady=5)
        
        ttk.Button(control_frame, text="Convert to CSV", command=self.convert_episodes).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Clear", command=lambda: self.episode_input_text.delete(1.0, tk.END)).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Load Sample", command=self.load_sample_episodes).pack(side=tk.LEFT, padx=5)
        
        # Output section
        output_frame = ttk.LabelFrame(self.episode_tab, text="CSV Preview", padding=10)
        output_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # CSV preview
        self.csv_preview_text = scrolledtext.ScrolledText(output_frame, height=10, wrap=tk.WORD)
        self.csv_preview_text.pack(fill="both", expand=True, pady=5)
        
        # Save/Load buttons
        save_frame = ttk.Frame(output_frame)
        save_frame.pack(fill="x", pady=5)
        
        ttk.Button(save_frame, text="Import CSV", command=self.import_episode_csv).pack(side=tk.LEFT, padx=5)
        ttk.Button(save_frame, text="Export CSV", command=self.export_episode_csv).pack(side=tk.LEFT, padx=5)
        ttk.Separator(save_frame, orient='vertical').pack(side=tk.LEFT, fill='y', padx=10)
        ttk.Button(save_frame, text="Load into Main Tab", command=self.load_csv_to_main).pack(side=tk.LEFT, padx=5)
        
    def convert_episodes(self):
        """Convert pasted episode list to CSV format"""
        input_text = self.episode_input_text.get(1.0, tk.END).strip()
        if not input_text:
            tk.messagebox.showwarning("Warning", "Please paste an episode list first!")
            return
        
        episodes = []
        lines = input_text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Try different patterns
            episode_info = self.parse_episode_line(line)
            if episode_info:
                episodes.append(episode_info)
        
        if not episodes:
            tk.messagebox.showerror("Error", "Could not parse any episodes. Please check the format.")
            return
        
        # Generate CSV content
        csv_content = "SeasonNumber,EpisodeNumber,EpisodeName,AbbvCombo\n"
        for ep in episodes:
            abbv = f"S{ep['season']:02d}E{ep['episode']:02d}"
            csv_content += f"{ep['season']},{ep['episode']},{ep['title']},{abbv}\n"
        
        self.csv_preview_text.delete(1.0, tk.END)
        self.csv_preview_text.insert(1.0, csv_content)
        
        self.update_status(f"Converted {len(episodes)} episodes to CSV format")
        
    def parse_episode_line(self, line):
        """Parse a single episode line using various patterns"""
        import re
        
        # Pattern 1: S01E01 - Title or 1x01 - Title
        pattern1 = r'[Ss]?(\d+)[xXeE](\d+)\s*[-–]\s*(.+)'
        match = re.match(pattern1, line)
        if match:
            return {
                'season': int(match.group(1)),
                'episode': int(match.group(2)),
                'title': match.group(3).strip().strip('"')
            }
        
        # Pattern 2: Season 1, Episode 1: Title
        pattern2 = r'Season\s*(\d+),?\s*Episode\s*(\d+):?\s*(.+)'
        match = re.match(pattern2, line, re.IGNORECASE)
        if match:
            return {
                'season': int(match.group(1)),
                'episode': int(match.group(2)),
                'title': match.group(3).strip().strip('"')
            }
        
        # Pattern 3: 1. Title (use default season)
        pattern3 = r'^(\d+)\.\s*(.+)'
        match = re.match(pattern3, line)
        if match:
            return {
                'season': self.default_season_var.get(),
                'episode': int(match.group(1)),
                'title': match.group(2).strip().strip('"')
            }
        
        # Pattern 4: "Title" (S1E1) or (1x01)
        pattern4 = r'["\'](.+?)["\']\s*\([Ss]?(\d+)[xXeE](\d+)\)'
        match = re.match(pattern4, line)
        if match:
            return {
                'season': int(match.group(2)),
                'episode': int(match.group(3)),
                'title': match.group(1).strip()
            }
        
        # Pattern 5: Episode 1: Title (use default season)
        pattern5 = r'Episode\s*(\d+):?\s*(.+)'
        match = re.match(pattern5, line, re.IGNORECASE)
        if match:
            return {
                'season': self.default_season_var.get(),
                'episode': int(match.group(1)),
                'title': match.group(2).strip().strip('"')
            }
        
        return None
        
    def load_sample_episodes(self):
        """Load a sample episode list for testing"""
        sample = """S01E01 - Downtown as Fruits
S01E02 - Eugene's Bike
S01E03 - The Little Pink Book
S01E04 - Field Trip
S01E05 - Arnold's Hat

Or try this format:

1. Pilot Episode
2. The Big Game
3. Mystery at School
4. Summer Vacation
5. The New Kid"""
        
        self.episode_input_text.delete(1.0, tk.END)
        self.episode_input_text.insert(1.0, sample)
        
    def save_episode_csv(self):
        """Save the generated CSV to a file"""
        csv_content = self.csv_preview_text.get(1.0, tk.END).strip()
        if not csv_content or csv_content == "":
            tk.messagebox.showwarning("Warning", "No CSV content to save!")
            return
            
        # Suggest filename based on show name
        show_name = self.show_name_var.get()
        if show_name:
            default_filename = f"{show_name.lower().replace(' ', '_')}_episodes.csv"
        else:
            default_filename = "episode_list.csv"
            
        file = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=default_filename,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if file:
            with open(file, 'w', encoding='utf-8') as f:
                f.write(csv_content)
            self.update_status(f"Episode list saved to {os.path.basename(file)}")
            
    def import_episode_csv(self):
        """Import an existing CSV file into the Episode Manager"""
        file = filedialog.askopenfilename(
            title="Import Episode CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if file:
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    csv_content = f.read()
                
                # Validate it's a proper episode CSV
                if "SeasonNumber,EpisodeNumber,EpisodeName" not in csv_content:
                    tk.messagebox.showerror("Error", "This doesn't appear to be a valid episode CSV file. "
                                           "It should contain SeasonNumber, EpisodeNumber, and EpisodeName columns.")
                    return
                
                # Load into preview
                self.csv_preview_text.delete(1.0, tk.END)
                self.csv_preview_text.insert(1.0, csv_content)
                
                # Try to extract show name from filename
                filename = os.path.basename(file)
                if filename.endswith('_episodes.csv'):
                    show_name = filename[:-13].replace('_', ' ').title()
                    self.show_name_var.set(show_name)
                
                self.update_status(f"Imported episode list from {os.path.basename(file)}")
                
                # Also convert back to text format for the input area
                self.convert_csv_to_text(csv_content)
                
            except Exception as e:
                tk.messagebox.showerror("Error", f"Failed to import CSV: {str(e)}")
                
    def export_episode_csv(self):
        """Export the current CSV preview to a file"""
        csv_content = self.csv_preview_text.get(1.0, tk.END).strip()
        if not csv_content or csv_content == "":
            tk.messagebox.showwarning("Warning", "No CSV content to export!")
            return
            
        # Create episode_lists directory if it doesn't exist
        episode_dir = os.path.join(os.path.dirname(__file__), 'episode_lists')
        os.makedirs(episode_dir, exist_ok=True)
        
        # Suggest filename based on show name
        show_name = self.show_name_var.get()
        if show_name:
            default_filename = f"{show_name.lower().replace(' ', '_')}_episodes.csv"
        else:
            default_filename = "episode_list.csv"
            
        file = filedialog.asksaveasfilename(
            title="Export Episode CSV",
            initialdir=episode_dir,
            defaultextension=".csv",
            initialfile=default_filename,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if file:
            with open(file, 'w', encoding='utf-8') as f:
                f.write(csv_content)
            self.update_status(f"Episode list exported to {os.path.basename(file)}")
            
    def convert_csv_to_text(self, csv_content):
        """Convert CSV content back to text format for display"""
        try:
            lines = csv_content.strip().split('\n')
            if len(lines) < 2:
                return
                
            # Skip header
            episode_lines = []
            for line in lines[1:]:
                parts = line.split(',')
                if len(parts) >= 3:
                    season = parts[0].strip()
                    episode = parts[1].strip()
                    # Handle titles with commas
                    title = ','.join(parts[2:-1]).strip('"')
                    if not title:
                        title = parts[2].strip('"')
                    
                    episode_lines.append(f"S{season.zfill(2)}E{episode.zfill(2)} - {title}")
            
            # Update input text area
            self.episode_input_text.delete(1.0, tk.END)
            self.episode_input_text.insert(1.0, '\n'.join(episode_lines))
            
        except Exception as e:
            logging.error(f"Error converting CSV to text: {e}")
            
    def load_csv_to_main(self):
        """Load the generated CSV into the main tab"""
        csv_content = self.csv_preview_text.get(1.0, tk.END).strip()
        if not csv_content:
            tk.messagebox.showwarning("Warning", "No CSV content to load!")
            return
            
        # Save to a temporary file and load it
        temp_file = os.path.join(tempfile.gettempdir(), "temp_episode_list.csv")
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(csv_content)
            
        self.episode_csv.set(temp_file)
        self.notebook.select(0)  # Switch to main tab
        self.update_status("Episode list loaded into main tab")

def main():
    root = tk.Tk()
    
    # Try to use a modern theme if available
    try:
        root.tk.call("source", "azure.tcl")
        root.tk.call("set_theme", "dark")
    except:
        # Fall back to default ttk theme
        style = ttk.Style()
        style.theme_use('clam')
    
    app = VideoSplitterGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()