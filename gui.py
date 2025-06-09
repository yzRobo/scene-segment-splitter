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
import traceback

from video_processor_gui import VideoProcessorGUI
from episode_formatter import EpisodeFormatter

class VideoSplitterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Scene Segment Splitter")
        self.root.geometry("900x750")
        
        # Initialize variables
        self.input_folder = tk.StringVar(value="input_videos")
        self.output_folder = tk.StringVar(value="output_videos")
        self.episode_csv = tk.StringVar(value="episode_list.csv")
        self.intro_duration = tk.IntVar(value=47)
        self.processing = False
        self.processor_thread = None
        self.log_queue = queue.Queue()
        
        self.create_widgets()
        self.root.after(100, self.check_log_queue)
        
    def create_widgets(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.main_tab = ttk.Frame(self.notebook); self.notebook.add(self.main_tab, text="Main"); self.create_main_tab()
        self.config_tab = ttk.Frame(self.notebook); self.notebook.add(self.config_tab, text="Configuration"); self.create_config_tab()
        self.episode_tab = ttk.Frame(self.notebook); self.notebook.add(self.episode_tab, text="Episode Manager"); self.create_episode_tab()
        
        self.status_bar = ttk.Label(self.root, text="Ready", relief=tk.SUNKEN); self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
    def create_main_tab(self):
        folder_frame = ttk.LabelFrame(self.main_tab, text="Folders", padding=10); folder_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(folder_frame, text="Input Folder:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(folder_frame, textvariable=self.input_folder, width=50).grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(folder_frame, text="Browse", command=lambda: self.browse_folder(self.input_folder)).grid(row=0, column=2, padx=5, pady=5)
        ttk.Label(folder_frame, text="Output Folder:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(folder_frame, textvariable=self.output_folder, width=50).grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(folder_frame, text="Browse", command=lambda: self.browse_folder(self.output_folder)).grid(row=1, column=2, padx=5, pady=5)
        ttk.Label(folder_frame, text="Episode CSV:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(folder_frame, textvariable=self.episode_csv, width=50).grid(row=2, column=1, padx=5, pady=5)
        ttk.Button(folder_frame, text="Browse", command=self.browse_csv).grid(row=2, column=2, padx=5, pady=5)
        
        control_frame = ttk.Frame(self.main_tab); control_frame.pack(fill="x", padx=10, pady=10)
        self.process_button = ttk.Button(control_frame, text="Start Processing", command=self.start_processing, style="Accent.TButton"); self.process_button.pack(side=tk.LEFT, padx=5)
        self.stop_button = ttk.Button(control_frame, text="Stop", command=self.stop_processing, state=tk.DISABLED); self.stop_button.pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Clear Log", command=self.clear_log).pack(side=tk.RIGHT, padx=5)
        
        self.progress = ttk.Progressbar(self.main_tab, mode='determinate'); self.progress.pack(fill="x", padx=10, pady=5)
        log_frame = ttk.LabelFrame(self.main_tab, text="Processing Log", padding=10); log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=20, wrap=tk.WORD); self.log_text.pack(fill="both", expand=True)
        
    def create_config_tab(self):
        basic_frame = ttk.LabelFrame(self.config_tab, text="Basic Settings", padding=10); basic_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(basic_frame, text="Intro Duration (seconds):").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        ttk.Spinbox(basic_frame, from_=0, to=300, textvariable=self.intro_duration, width=10).grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        detection_frame = ttk.LabelFrame(self.config_tab, text="Detection and Splitting", padding=10); detection_frame.pack(fill="x", padx=10, pady=5)
        
        self.target_time = tk.IntVar(value=710)
        ttk.Label(detection_frame, text="Target Time (s):").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        ttk.Spinbox(detection_frame, from_=0, to=7200, textvariable=self.target_time, width=10).grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        self.time_margin = tk.IntVar(value=60)
        ttk.Label(detection_frame, text="Time Margin (±s):").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        ttk.Spinbox(detection_frame, from_=0, to=600, textvariable=self.time_margin, width=10).grid(row=1, column=1, padx=5, pady=5, sticky="w")
        
        self.transition_selection_var = tk.StringVar(value="Select Latest Transition")
        ttk.Label(detection_frame, text="Transition Logic:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        ttk.Combobox(detection_frame, textvariable=self.transition_selection_var, values=["Select Latest Transition", "Select Earliest Transition"], width=22, state="readonly").grid(row=2, column=1, padx=5, pady=5, sticky="w")

        self.split_point_var = tk.StringVar(value="At Start of Fade")
        ttk.Label(detection_frame, text="Split Point:").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        ttk.Combobox(detection_frame, textvariable=self.split_point_var, values=["At Start of Fade", "After Fade"], width=22, state="readonly").grid(row=3, column=1, padx=5, pady=5, sticky="w")

        adv_frame = ttk.LabelFrame(self.config_tab, text="Advanced Detection Parameters", padding=10); adv_frame.pack(fill="x", padx=10, pady=5)
        self.black_duration = tk.StringVar(value="0.2"); self.pixel_threshold = tk.StringVar(value="0.15"); self.picture_threshold = tk.StringVar(value="0.95")
        ttk.Label(adv_frame, text="Black Duration:").grid(row=0, column=0, sticky="w", padx=5, pady=5); ttk.Entry(adv_frame, textvariable=self.black_duration, width=10).grid(row=0, column=1, sticky="w", padx=5, pady=5)
        ttk.Label(adv_frame, text="Pixel Threshold:").grid(row=1, column=0, sticky="w", padx=5, pady=5); ttk.Entry(adv_frame, textvariable=self.pixel_threshold, width=10).grid(row=1, column=1, sticky="w", padx=5, pady=5)
        ttk.Label(adv_frame, text="Picture Threshold:").grid(row=2, column=0, sticky="w", padx=5, pady=5); ttk.Entry(adv_frame, textvariable=self.picture_threshold, width=10).grid(row=2, column=1, sticky="w", padx=5, pady=5)
        
        config_control_frame = ttk.Frame(self.config_tab); config_control_frame.pack(fill="x", padx=10, pady=10, side=tk.BOTTOM)
        ttk.Button(config_control_frame, text="Save Configuration", command=self.save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(config_control_frame, text="Load Configuration", command=self.load_config).pack(side=tk.LEFT, padx=5)

    def browse_folder(self, var): folder = filedialog.askdirectory(initialdir=var.get()); _ = var.set(folder) if folder else None
    def browse_csv(self): file = filedialog.askopenfilename(initialdir=os.path.dirname(self.episode_csv.get()), filetypes=[("CSV files", "*.csv")]); _ = self.episode_csv.set(file) if file else None
    def clear_log(self): self.log_text.delete(1.0, tk.END)
    def update_status(self, message): self.status_bar.config(text=message)
    def log_message(self, message, percentage=None): self.log_queue.put((message, percentage))
        
    def check_log_queue(self):
        try:
            while True:
                message, percentage = self.log_queue.get_nowait()
                if message: self.log_text.insert(tk.END, message + "\n"); self.log_text.see(tk.END)
                if percentage is not None: self.progress['value'] = percentage
        except queue.Empty: pass
        finally: self.root.after(100, self.check_log_queue)
            
    def start_processing(self):
        if self.processing: return
        if not os.path.exists(self.input_folder.get()): tk.messagebox.showerror("Error", "Input folder does not exist!"); return
        if not os.path.exists(self.episode_csv.get()): tk.messagebox.showerror("Error", "Episode CSV file does not exist!"); return
        self.processing = True; self.process_button.config(state=tk.DISABLED); self.stop_button.config(state=tk.NORMAL)
        self.progress['value'] = 0; self.update_status("Processing...")
        self.processor_thread = threading.Thread(target=self.run_processor, daemon=True); self.processor_thread.start()
        
    def stop_processing(self):
        if self.processing and self.processor_thread.is_alive():
            self.update_status("Stopping..."); _ = self.processor_instance.cancel_processing() if hasattr(self, 'processor_instance') else None
        
    def run_processor(self):
        try:
            import logging
            class GUILogHandler(logging.Handler):
                def __init__(self, gui): super().__init__(); self.gui = gui
                def emit(self, record): self.gui.log_message(self.format(record), None)
            log_handler = GUILogHandler(self); log_handler.setFormatter(logging.Formatter('%(message)s'))
            logger = logging.getLogger(); logger.handlers = []; logger.addHandler(log_handler); logger.setLevel(logging.INFO)
            current_config = self.get_current_config()
            self.processor_instance = VideoProcessorGUI(self.input_folder.get(), self.output_folder.get(), config=current_config)
            self.processor_instance.set_progress_callback(self.log_message)
            self.processor_instance.process_videos()
            status = "Processing cancelled." if self.processor_instance.cancel_requested else "Processing completed!"
            self.update_status(status)
        except Exception as e: self.log_message(f"CRITICAL ERROR: {str(e)}\n{traceback.format_exc()}"); self.update_status("Processing failed!")
        finally: self.processing = False; self.root.after(0, self.on_processing_finished)

    def on_processing_finished(self):
        self.process_button.config(state=tk.NORMAL); self.stop_button.config(state=tk.DISABLED)
        if hasattr(self, 'processor_instance') and not self.processor_instance.cancel_requested: self.progress['value'] = 100

    def get_current_config(self):
        return {
            "input_folder": self.input_folder.get(), "output_folder": self.output_folder.get(),
            "episode_csv": self.episode_csv.get(), "intro_duration": self.intro_duration.get(),
            "target_time": self.target_time.get(), "time_margin": self.time_margin.get(),
            "black_duration": self.black_duration.get(), "pixel_threshold": self.pixel_threshold.get(),
            "picture_threshold": self.picture_threshold.get(), 
            "transition_selection": self.transition_selection_var.get(), "split_point": self.split_point_var.get()
        }
            
    def save_config(self):
        config = self.get_current_config()
        configs_dir = os.path.join(os.path.dirname(__file__), 'configs'); os.makedirs(configs_dir, exist_ok=True)
        file = filedialog.asksaveasfilename(initialdir=configs_dir, defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if file:
            with open(file, 'w') as f: json.dump(config, f, indent=4)
            self.update_status(f"Configuration saved to {os.path.basename(file)}")
            
    def load_config(self):
        configs_dir = os.path.join(os.path.dirname(__file__), 'configs'); os.makedirs(configs_dir, exist_ok=True)
        file = filedialog.askopenfilename(initialdir=configs_dir, filetypes=[("JSON files", "*.json")])
        if file:
            try:
                with open(file, 'r') as f: config = json.load(f)
                self.input_folder.set(config.get("input_folder", "input_videos"))
                self.output_folder.set(config.get("output_folder", "output_videos"))
                self.episode_csv.set(config.get("episode_csv", "episode_list.csv"))
                self.intro_duration.set(config.get("intro_duration", 47))
                self.target_time.set(config.get("target_time", 710))
                self.time_margin.set(config.get("time_margin", 60))
                self.black_duration.set(config.get("black_duration", "0.2"))
                self.pixel_threshold.set(config.get("pixel_threshold", "0.15"))
                self.picture_threshold.set(config.get("picture_threshold", "0.95"))
                self.transition_selection_var.set(config.get("transition_selection", "Select Latest Transition"))
                self.split_point_var.set(config.get("split_point", "At Start of Fade"))
                self.update_status(f"Configuration loaded from {os.path.basename(file)}")
            except Exception as e: tk.messagebox.showerror("Error", f"Failed to load configuration: {str(e)}")
    
    def create_episode_tab(self):
        instructions_frame=ttk.LabelFrame(self.episode_tab,text="Instructions",padding=10);instructions_frame.pack(fill="x",padx=10,pady=5)
        instructions_text="""Paste your episode list in one of these formats:
1. "S01E01 - Episode Title" or "1x01 - Episode Title"
2. "Season 1, Episode 1: Episode Title"
3. Simple numbered list: "1. Episode Title" (specify season)
4. Copy from Wikipedia, IMDB, TheTVDB, etc."""
        ttk.Label(instructions_frame,text=instructions_text,wraplength=850,justify="left").pack(pady=5,anchor='w')
        input_frame=ttk.LabelFrame(self.episode_tab,text="Paste Episode List",padding=10);input_frame.pack(fill="both",expand=True,padx=10,pady=5)
        name_frame=ttk.Frame(input_frame);name_frame.pack(fill="x",pady=(0,10))
        ttk.Label(name_frame,text="Show Name (optional):").pack(side=tk.LEFT,padx=5)
        self.show_name_var=tk.StringVar();ttk.Entry(name_frame,textvariable=self.show_name_var,width=30).pack(side=tk.LEFT,padx=5)
        ttk.Label(name_frame,text="Default Season:").pack(side=tk.LEFT,padx=(20,5))
        self.default_season_var=tk.IntVar(value=1);ttk.Spinbox(name_frame,from_=1,to=100,textvariable=self.default_season_var,width=5).pack(side=tk.LEFT)
        self.episode_input_text=scrolledtext.ScrolledText(input_frame,height=10,wrap=tk.WORD);self.episode_input_text.pack(fill="both",expand=True,pady=5)
        control_frame=ttk.Frame(input_frame);control_frame.pack(fill="x",pady=5)
        ttk.Button(control_frame,text="Convert to CSV",command=self.convert_episodes).pack(side=tk.LEFT,padx=5)
        ttk.Button(control_frame,text="Clear",command=lambda:self.episode_input_text.delete(1.0,tk.END)).pack(side=tk.LEFT,padx=5)
        ttk.Button(control_frame,text="Load Sample",command=self.load_sample_episodes).pack(side=tk.LEFT,padx=5)
        output_frame=ttk.LabelFrame(self.episode_tab,text="CSV Preview",padding=10);output_frame.pack(fill="both",expand=True,padx=10,pady=5)
        self.csv_preview_text=scrolledtext.ScrolledText(output_frame,height=10,wrap=tk.WORD);self.csv_preview_text.pack(fill="both",expand=True,pady=5)
        save_frame=ttk.Frame(output_frame);save_frame.pack(fill="x",pady=5)
        ttk.Button(save_frame,text="Import CSV",command=self.import_episode_csv).pack(side=tk.LEFT,padx=5)
        ttk.Button(save_frame,text="Export CSV",command=self.export_episode_csv).pack(side=tk.LEFT,padx=5)
        ttk.Separator(save_frame,orient='vertical').pack(side=tk.LEFT,fill='y',padx=10)
        ttk.Button(save_frame,text="Load into Main Tab",command=self.load_csv_to_main).pack(side=tk.LEFT,padx=5)

    def convert_episodes(self): input_text=self.episode_input_text.get(1.0,tk.END).strip();_=(lambda f,e:self.csv_preview_text.delete(1.0,tk.END) or self.csv_preview_text.insert(1.0,f.generate_csv(e)) or self.update_status(f"Converted {len(e)} episodes"))(EpisodeFormatter(),EpisodeFormatter().parse_episode_list(input_text,default_season=self.default_season_var.get())) if input_text else tk.messagebox.showwarning("Warning","Paste an episode list first!")
    def load_sample_episodes(self): self.episode_input_text.delete(1.0,tk.END);self.episode_input_text.insert(1.0,"S01E01 - Downtown as Fruits\nS01E02 - Eugene's Bike\n\nOr try this (set Default Season above):\n\n1. Pilot Episode\n2. The Big Game")
    def import_episode_csv(self): file=filedialog.askopenfilename(title="Import Episode CSV",filetypes=[("CSV files","*.csv")]);_=(lambda c:self.csv_preview_text.delete(1.0,tk.END) or self.csv_preview_text.insert(1.0,c) or self.update_status(f"Imported from {os.path.basename(file)}"))(open(file,'r',encoding='utf-8').read()) if file else None
    def export_episode_csv(self): csv_content=self.csv_preview_text.get(1.0,tk.END).strip();_=(lambda d,f:open(f,'w',encoding='utf-8').write(csv_content) or self.update_status(f"Exported to {os.path.basename(f)}"))(os.path.join(os.path.dirname(__file__),'episode_lists'),filedialog.asksaveasfilename(title="Export Episode CSV",initialdir=os.path.join(os.path.dirname(__file__),'episode_lists'),defaultextension=".csv",initialfile=f"{self.show_name_var.get().lower().replace(' ','_')}_episodes.csv" if self.show_name_var.get() else "episode_list.csv")) if csv_content else tk.messagebox.showwarning("Warning","No CSV content to export!")
    def load_csv_to_main(self): csv_content=self.csv_preview_text.get(1.0,tk.END).strip();_=(lambda t:open(t,'w',encoding='utf-8').write(csv_content) or self.episode_csv.set(t) or self.notebook.select(0) or self.update_status("Loaded into Main tab"))(os.path.join(tempfile.gettempdir(),f"temp_episode_list_{int(datetime.now().timestamp())}.csv")) if csv_content else tk.messagebox.showwarning("Warning","No CSV content to load!")

def main():
    root = tk.Tk()
    try:
        azure_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'azure.tcl')
        if os.path.exists(azure_path): root.tk.call("source", azure_path); root.tk.call("set_theme", "dark")
        else: ttk.Style().theme_use('clam')
    except tk.TclError: print("Could not apply custom theme.")
    app = VideoSplitterGUI(root); root.mainloop()

if __name__ == "__main__": main()