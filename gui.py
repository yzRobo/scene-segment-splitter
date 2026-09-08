"""
gui.py - Scene Segment Splitter GUI

A modern tkinter front-end for the shared VideoProcessor engine:
  * pick input/output folders and an episode-list CSV,
  * tune detection (or let it auto-derive the boundary),
  * watch real-time progress, and
  * build episode-list CSVs from pasted text.

Threading: all Tk widget access happens on the main thread. The worker thread
only pushes messages onto a queue (drained by check_ui_queue via root.after) and
schedules completion via root.after - it never touches a widget directly.

Theme: uses the Sun Valley ttk theme (sv-ttk) when installed, with a light/dark
toggle, and falls back gracefully to a built-in ttk theme otherwise.
"""

import os
import sys
import json
import queue
import tempfile
import threading
import traceback
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from tkinter import ttk, filedialog, scrolledtext, messagebox

from video_processor_gui import VideoProcessorGUI
from episode_formatter import EpisodeFormatter

APP_DIR = os.path.dirname(os.path.abspath(__file__))

DETECTION_METHODS = [
    "Comprehensive (All Methods)",
    "Standard Blackdetect Only",
    "Histogram Analysis",
    "Scene Change Detection",
]
TRANSITION_MODES = ["Smart", "Select Latest Transition", "Select Earliest Transition"]
SPLIT_POINTS = ["At Start of Fade", "After Fade"]
FAILURE_MODES = ["copy", "midpoint", "skip"]


class VideoSplitterGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Scene Segment Splitter")
        self.root.geometry("980x880")
        self.root.minsize(820, 640)

        # State
        self.input_folder = tk.StringVar(value="input_videos")
        self.output_folder = tk.StringVar(value="output_videos")
        self.episode_csv = tk.StringVar(value="episode_list.csv")
        self.intro_duration = tk.IntVar(value=47)
        self.auto_target = tk.BooleanVar(value=True)
        self.target_time = tk.IntVar(value=710)
        self.time_margin = tk.IntVar(value=120)
        self.black_duration = tk.StringVar(value="0.2")
        self.pixel_threshold = tk.StringVar(value="0.15")
        self.picture_threshold = tk.StringVar(value="0.95")
        self.detection_method_var = tk.StringVar(value=DETECTION_METHODS[0])
        self.transition_selection_var = tk.StringVar(value=TRANSITION_MODES[0])
        self.split_point_var = tk.StringVar(value=SPLIT_POINTS[0])
        self.failure_mode_var = tk.StringVar(value=FAILURE_MODES[0])

        self.processing = False
        self.processor_thread = None
        self.processor_instance = None
        self.ui_queue: "queue.Queue" = queue.Queue()
        self._last_temp_csv = None

        self._init_theme()
        self._init_fonts()
        self._build_ui()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self.check_ui_queue)

    # ---------------------------------------------------------------- theme
    def _init_theme(self):
        self._sv_ttk = None
        try:
            import sv_ttk
            sv_ttk.set_theme("dark")
            self._sv_ttk = sv_ttk
        except Exception:
            try:
                ttk.Style().theme_use("clam")
            except tk.TclError:
                pass

    def _init_fonts(self):
        self.font_title = tkfont.Font(family="Segoe UI", size=20, weight="bold")
        self.font_sub = tkfont.Font(family="Segoe UI", size=10)
        self.font_mono = tkfont.Font(family="Consolas", size=10)
        style = ttk.Style()
        style.configure("Title.TLabel", font=self.font_title)
        style.configure("Sub.TLabel", font=self.font_sub, foreground="#8a8a8a")
        style.configure("Section.TLabelframe.Label", font=("Segoe UI", 10, "bold"))

    def toggle_theme(self):
        if self._sv_ttk:
            self._sv_ttk.toggle_theme()
            self.theme_btn.config(
                text="☀  Light" if self._sv_ttk.get_theme() == "dark" else "🌙  Dark")

    # ------------------------------------------------------------------- UI
    def _build_ui(self):
        header = ttk.Frame(self.root, padding=(16, 12, 16, 4))
        header.pack(fill="x")
        titles = ttk.Frame(header)
        titles.pack(side=tk.LEFT)
        ttk.Label(titles, text="Scene Segment Splitter", style="Title.TLabel").pack(anchor="w")
        ttk.Label(titles, text="Split double-episode video files into correctly named single episodes",
                  style="Sub.TLabel").pack(anchor="w")
        if self._sv_ttk:
            self.theme_btn = ttk.Button(header, text="☀  Light", width=10, command=self.toggle_theme)
            self.theme_btn.pack(side=tk.RIGHT, anchor="n")

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=(8, 8))
        self.main_tab = ttk.Frame(self.notebook)
        self.config_tab = ttk.Frame(self.notebook)
        self.episode_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.main_tab, text="  Process  ")
        self.notebook.add(self.config_tab, text="  Configuration  ")
        self.notebook.add(self.episode_tab, text="  Episode Manager  ")
        self._build_main_tab()
        self._build_config_tab()
        self._build_episode_tab()

        self.status_bar = ttk.Label(self.root, text="Ready", relief=tk.SUNKEN, anchor="w", padding=(10, 4))
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _build_main_tab(self):
        folders = ttk.LabelFrame(self.main_tab, text="Folders & Episode List",
                                 style="Section.TLabelframe", padding=12)
        folders.pack(fill="x", padx=12, pady=(12, 6))
        folders.columnconfigure(1, weight=1)
        self._path_row(folders, 0, "Input folder", self.input_folder,
                       lambda: self._browse_folder(self.input_folder))
        self._path_row(folders, 1, "Output folder", self.output_folder,
                       lambda: self._browse_folder(self.output_folder))
        self._path_row(folders, 2, "Episode CSV", self.episode_csv, self._browse_csv)

        controls = ttk.Frame(self.main_tab, padding=(12, 6))
        controls.pack(fill="x")
        self.process_button = ttk.Button(controls, text="▶  Start Processing",
                                         command=self.start_processing, style="Accent.TButton")
        self.process_button.pack(side=tk.LEFT)
        self.stop_button = ttk.Button(controls, text="■  Stop", command=self.stop_processing,
                                      state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(controls, text="Clear Log", command=self.clear_log).pack(side=tk.RIGHT)

        prog = ttk.Frame(self.main_tab, padding=(12, 0))
        prog.pack(fill="x")
        self.progress = ttk.Progressbar(prog, mode="determinate")
        self.progress.pack(side=tk.LEFT, fill="x", expand=True)
        self.progress_label = ttk.Label(prog, text="0%", width=6, anchor="e")
        self.progress_label.pack(side=tk.LEFT, padx=(8, 0))

        logf = ttk.LabelFrame(self.main_tab, text="Processing Log",
                              style="Section.TLabelframe", padding=8)
        logf.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        self.log_text = scrolledtext.ScrolledText(logf, height=18, wrap=tk.WORD,
                                                  font=self.font_mono, relief="flat",
                                                  borderwidth=0)
        self.log_text.pack(fill="both", expand=True)

    def _path_row(self, parent, row, label, var, command):
        ttk.Label(parent, text=label + ":").grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", pady=4)
        ttk.Button(parent, text="Browse…", command=command, width=10).grid(
            row=row, column=2, padx=(8, 0), pady=4)

    def _build_config_tab(self):
        outer = ttk.Frame(self.config_tab, padding=12)
        outer.pack(fill="both", expand=True)

        basic = ttk.LabelFrame(outer, text="Episode & Boundary",
                               style="Section.TLabelframe", padding=12)
        basic.pack(fill="x", pady=(0, 8))
        self._spin_row(basic, 0, "Intro duration (s)", self.intro_duration, 0, 600,
                       "Shared intro re-inserted at the start of every episode after the first.")
        ttk.Checkbutton(basic, text="Auto-detect boundary from runtime  (recommended)",
                        variable=self.auto_target, command=self._sync_target_state).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(6, 2))
        self._spin_row(basic, 2, "Target time (s)", self.target_time, 0, 7200,
                       "Manual expected boundary; used only when auto-detect is off.")
        self._spin_row(basic, 3, "Search margin (±s)", self.time_margin, 0, 900,
                       "How far from the expected boundary to search for a fade.")

        det = ttk.LabelFrame(outer, text="Detection & Splitting",
                             style="Section.TLabelframe", padding=12)
        det.pack(fill="x", pady=(0, 8))
        self._combo_row(det, 0, "Detection method", self.detection_method_var, DETECTION_METHODS,
                        "Comprehensive falls back through methods if one finds nothing.")
        self._combo_row(det, 1, "Transition logic", self.transition_selection_var, TRANSITION_MODES,
                        "Smart favors the long fade nearest the expected boundary.")
        self._combo_row(det, 2, "Split point", self.split_point_var, SPLIT_POINTS,
                        "Whether the fade-to-black stays with episode 2 or is dropped.")
        self._combo_row(det, 3, "If no boundary found", self.failure_mode_var, FAILURE_MODES,
                        "copy = keep source unsplit · midpoint = split at estimate · skip.")

        adv = ttk.LabelFrame(outer, text="Advanced blackdetect thresholds",
                             style="Section.TLabelframe", padding=12)
        adv.pack(fill="x", pady=(0, 8))
        self._entry_row(adv, 0, "Black duration (s)", self.black_duration,
                        "Minimum seconds a frame must stay black.")
        self._entry_row(adv, 1, "Pixel threshold", self.pixel_threshold,
                        "How dark a pixel counts as black (0=black … 1=white).")
        self._entry_row(adv, 2, "Picture threshold", self.picture_threshold,
                        "Fraction of the frame that must be black.")

        btns = ttk.Frame(outer)
        btns.pack(fill="x", pady=(4, 0))
        ttk.Button(btns, text="💾  Save Configuration", command=self.save_config).pack(side=tk.LEFT)
        ttk.Button(btns, text="📂  Load Configuration", command=self.load_config).pack(side=tk.LEFT, padx=(8, 0))
        self._sync_target_state()

    def _spin_row(self, parent, row, label, var, lo, hi, hint):
        parent.columnconfigure(2, weight=1)
        ttk.Label(parent, text=label + ":").grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        sp = ttk.Spinbox(parent, from_=lo, to=hi, textvariable=var, width=10)
        sp.grid(row=row, column=1, sticky="w", pady=4)
        ttk.Label(parent, text=hint, style="Sub.TLabel").grid(row=row, column=2, sticky="w", padx=(12, 0))
        return sp

    def _combo_row(self, parent, row, label, var, values, hint):
        parent.columnconfigure(2, weight=1)
        ttk.Label(parent, text=label + ":").grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(parent, textvariable=var, values=values, state="readonly", width=28).grid(
            row=row, column=1, sticky="w", pady=4)
        ttk.Label(parent, text=hint, style="Sub.TLabel").grid(row=row, column=2, sticky="w", padx=(12, 0))

    def _entry_row(self, parent, row, label, var, hint):
        parent.columnconfigure(2, weight=1)
        ttk.Label(parent, text=label + ":").grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=var, width=12).grid(row=row, column=1, sticky="w", pady=4)
        ttk.Label(parent, text=hint, style="Sub.TLabel").grid(row=row, column=2, sticky="w", padx=(12, 0))

    def _sync_target_state(self):
        # (Visual hint only) target_time is honored only when auto-detect is off.
        pass

    def _build_episode_tab(self):
        outer = ttk.Frame(self.episode_tab, padding=12)
        outer.pack(fill="both", expand=True)
        instr = ttk.LabelFrame(outer, text="Build an episode list from pasted text",
                               style="Section.TLabelframe", padding=12)
        instr.pack(fill="x")
        ttk.Label(instr, justify="left", style="Sub.TLabel", text=(
            "Paste an episode list in any common format and click Convert:\n"
            "  •  S01E01 - Title   /   1x01 - Title\n"
            "  •  Season 1, Episode 1: Title\n"
            "  •  1. Title   (set a default season)\n"
            "  •  Wikipedia / IMDb / TheTVDB rows")).pack(anchor="w")

        meta = ttk.Frame(outer, padding=(0, 8))
        meta.pack(fill="x")
        ttk.Label(meta, text="Show name (optional):").pack(side=tk.LEFT)
        self.show_name_var = tk.StringVar()
        ttk.Entry(meta, textvariable=self.show_name_var, width=28).pack(side=tk.LEFT, padx=(6, 20))
        ttk.Label(meta, text="Default season:").pack(side=tk.LEFT)
        self.default_season_var = tk.IntVar(value=1)
        ttk.Spinbox(meta, from_=1, to=100, textvariable=self.default_season_var, width=5).pack(side=tk.LEFT, padx=6)

        panes = ttk.Frame(outer)
        panes.pack(fill="both", expand=True)
        panes.columnconfigure(0, weight=1)
        panes.columnconfigure(1, weight=1)
        panes.rowconfigure(1, weight=1)

        ttk.Label(panes, text="Paste episode list").grid(row=0, column=0, sticky="w")
        ttk.Label(panes, text="CSV preview").grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.episode_input_text = scrolledtext.ScrolledText(panes, height=14, wrap=tk.WORD, font=self.font_mono)
        self.episode_input_text.grid(row=1, column=0, sticky="nsew", pady=(2, 0))
        self.csv_preview_text = scrolledtext.ScrolledText(panes, height=14, wrap=tk.NONE, font=self.font_mono)
        self.csv_preview_text.grid(row=1, column=1, sticky="nsew", padx=(8, 0), pady=(2, 0))

        actions = ttk.Frame(outer, padding=(0, 10, 0, 0))
        actions.pack(fill="x")
        ttk.Button(actions, text="Convert to CSV ▶", command=self.convert_episodes,
                   style="Accent.TButton").pack(side=tk.LEFT)
        ttk.Button(actions, text="Load Sample", command=self.load_sample_episodes).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="Clear",
                   command=lambda: self.episode_input_text.delete(1.0, tk.END)).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Separator(actions, orient="vertical").pack(side=tk.LEFT, fill="y", padx=12)
        ttk.Button(actions, text="Import CSV…", command=self.import_episode_csv).pack(side=tk.LEFT)
        ttk.Button(actions, text="Export CSV…", command=self.export_episode_csv).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="Use in Process tab ▶", command=self.load_csv_to_main).pack(side=tk.RIGHT)

    # -------------------------------------------------------------- helpers
    def _browse_folder(self, var):
        folder = filedialog.askdirectory(initialdir=var.get() or ".")
        if folder:
            var.set(folder)

    def _browse_csv(self):
        start = os.path.dirname(self.episode_csv.get()) or "."
        file = filedialog.askopenfilename(initialdir=start, filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if file:
            self.episode_csv.set(file)

    def clear_log(self):
        self.log_text.delete(1.0, tk.END)

    def update_status(self, message):
        self.status_bar.config(text=message)

    # --------------------------------------------------------- thread-safe UI
    def on_progress(self, message, percentage=None):
        """Called from the worker thread (and log handler). Just enqueue."""
        self.ui_queue.put(("log", message, percentage))

    def check_ui_queue(self):
        try:
            while True:
                kind, payload, extra = self.ui_queue.get_nowait()
                if kind == "log":
                    if payload:
                        self.log_text.insert(tk.END, payload + "\n")
                        self.log_text.see(tk.END)
                    if extra is not None:
                        pct = max(0, min(100, int(extra)))
                        self.progress["value"] = pct
                        self.progress_label.config(text=f"{pct}%")
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.check_ui_queue)

    def _get_int(self, var, default):
        try:
            return int(var.get())
        except (tk.TclError, ValueError):
            return default

    def get_current_config(self):
        return {
            "input_folder": self.input_folder.get(),
            "output_folder": self.output_folder.get(),
            "episode_csv": self.episode_csv.get(),
            "intro_duration": self._get_int(self.intro_duration, 47),
            "auto_target": bool(self.auto_target.get()),
            "target_time": self._get_int(self.target_time, 710),
            "time_margin": self._get_int(self.time_margin, 120),
            "black_duration": self.black_duration.get() or "0.2",
            "pixel_threshold": self.pixel_threshold.get() or "0.15",
            "picture_threshold": self.picture_threshold.get() or "0.95",
            "transition_selection": self.transition_selection_var.get(),
            "split_point": self.split_point_var.get(),
            "detection_method": self.detection_method_var.get(),
            "on_detection_failure": self.failure_mode_var.get(),
        }

    # --------------------------------------------------------- processing
    def start_processing(self):
        if self.processing:
            return
        if not os.path.isdir(self.input_folder.get()):
            messagebox.showerror("Error", "Input folder does not exist!")
            return
        if not os.path.exists(self.episode_csv.get()):
            if not messagebox.askyesno(
                    "Episode CSV missing",
                    "The episode CSV was not found. Continue anyway?\n"
                    "(Output files will keep their original names when a title can't be matched.)"):
                return

        config = self.get_current_config()
        if not (config["output_folder"] or "").strip():
            messagebox.showerror("Error", "Please choose an output folder.")
            return

        # Install the log handler BEFORE constructing the processor so setup
        # diagnostics ("Loaded N episodes", CSV-not-found) reach the log.
        self._install_log_handler()

        # Build config + processor on the MAIN thread (no Tk access in worker).
        try:
            self.processor_instance = VideoProcessorGUI(
                config["input_folder"], config["output_folder"], config=config)
        except FileNotFoundError as e:
            # Distinguish a missing binary from a bad output path.
            msg = str(e)
            if "not found" in msg and ("ffmpeg" in msg or "ffprobe" in msg or "mkvmerge" in msg):
                messagebox.showerror("Missing dependency", msg)
            else:
                messagebox.showerror("Error", f"Could not start: {msg}")
            return
        except Exception as e:
            messagebox.showerror("Error", f"Could not start: {e}")
            return
        self.processor_instance.set_progress_callback(self.on_progress)

        self.processing = True
        self.process_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.progress["value"] = 0
        self.progress_label.config(text="0%")
        self.update_status("Processing…")

        self.processor_thread = threading.Thread(target=self.run_processor, daemon=True)
        self.processor_thread.start()

    def _install_log_handler(self):
        import logging
        gui = self

        class GUILogHandler(logging.Handler):
            def emit(self, record):
                gui.ui_queue.put(("log", self.format(record), None))

        handler = GUILogHandler()
        handler.setFormatter(__import__("logging").Formatter("%(message)s"))
        logger = logging.getLogger()
        logger.handlers = [handler]
        logger.setLevel(logging.INFO)

    def run_processor(self):
        try:
            self.processor_instance.process_videos()
        except Exception as e:
            self.ui_queue.put(("log", f"CRITICAL ERROR: {e}\n{traceback.format_exc()}", None))
        finally:
            self.root.after(0, self.on_processing_finished)

    def stop_processing(self):
        if self.processing and self.processor_instance:
            self.update_status("Stopping…")
            self.processor_instance.cancel_processing()

    def on_processing_finished(self):
        self.processing = False
        self.process_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        cancelled = bool(self.processor_instance and self.processor_instance.cancel_requested)
        if not cancelled:
            self.progress["value"] = 100
            self.progress_label.config(text="100%")
        self.update_status("Processing cancelled." if cancelled else "Processing complete.")

    def on_close(self):
        if self.processing:
            if not messagebox.askyesno("Quit", "Processing is running. Stop and quit?"):
                return
            if self.processor_instance:
                self.processor_instance.cancel_processing()
        self.root.destroy()

    # ----------------------------------------------------------- config I/O
    def save_config(self):
        configs_dir = os.path.join(APP_DIR, "configs")
        os.makedirs(configs_dir, exist_ok=True)
        file = filedialog.asksaveasfilename(initialdir=configs_dir, defaultextension=".json",
                                            filetypes=[("JSON files", "*.json")])
        if not file:
            return
        try:
            with open(file, "w", encoding="utf-8") as f:
                json.dump(self.get_current_config(), f, indent=4)
            self.update_status(f"Configuration saved to {os.path.basename(file)}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save configuration: {e}")

    def load_config(self):
        configs_dir = os.path.join(APP_DIR, "configs")
        os.makedirs(configs_dir, exist_ok=True)
        file = filedialog.askopenfilename(initialdir=configs_dir, filetypes=[("JSON files", "*.json")])
        if not file:
            return
        try:
            with open(file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load configuration: {e}")
            return
        self.input_folder.set(cfg.get("input_folder", "input_videos"))
        self.output_folder.set(cfg.get("output_folder", "output_videos"))
        self.episode_csv.set(cfg.get("episode_csv", "episode_list.csv"))
        self.intro_duration.set(cfg.get("intro_duration", 47))
        self.auto_target.set(cfg.get("auto_target", "target_time" not in cfg))
        self.target_time.set(cfg.get("target_time", 710))
        self.time_margin.set(cfg.get("time_margin", 120))
        self.black_duration.set(cfg.get("black_duration", "0.2"))
        self.pixel_threshold.set(cfg.get("pixel_threshold", "0.15"))
        self.picture_threshold.set(cfg.get("picture_threshold", "0.95"))
        self.detection_method_var.set(cfg.get("detection_method", DETECTION_METHODS[0]))
        self.transition_selection_var.set(cfg.get("transition_selection", TRANSITION_MODES[0]))
        self.split_point_var.set(cfg.get("split_point", SPLIT_POINTS[0]))
        self.failure_mode_var.set(cfg.get("on_detection_failure", FAILURE_MODES[0]))
        self._sync_target_state()
        self.update_status(f"Configuration loaded from {os.path.basename(file)}")

    # ------------------------------------------------------- episode manager
    def convert_episodes(self):
        text = self.episode_input_text.get(1.0, tk.END).strip()
        if not text:
            messagebox.showwarning("Nothing to convert", "Paste an episode list first!")
            return
        try:
            formatter = EpisodeFormatter()
            episodes = formatter.parse_episode_list(text, default_season=self._get_int(self.default_season_var, 1))
            csv_text = formatter.generate_csv(episodes)
        except Exception as e:
            messagebox.showerror("Error", f"Could not parse episode list: {e}")
            return
        self.csv_preview_text.delete(1.0, tk.END)
        self.csv_preview_text.insert(1.0, csv_text)
        self.update_status(f"Converted {len(episodes)} episode(s).")

    def load_sample_episodes(self):
        self.episode_input_text.delete(1.0, tk.END)
        self.episode_input_text.insert(1.0,
            "S01E01 - Downtown as Fruits\n"
            "S01E02 - Eugene's Bike\n\n"
            "Or a simple numbered list (set Default Season above):\n\n"
            "1. Pilot Episode\n2. The Big Game")

    def import_episode_csv(self):
        file = filedialog.askopenfilename(title="Import Episode CSV", filetypes=[("CSV files", "*.csv")])
        if not file:
            return
        content = None
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                with open(file, "r", encoding=enc) as f:
                    content = f.read()
                break
            except (UnicodeDecodeError, OSError):
                continue
        if content is None:
            messagebox.showerror("Error", "Could not read that CSV file.")
            return
        self.csv_preview_text.delete(1.0, tk.END)
        self.csv_preview_text.insert(1.0, content)
        self.update_status(f"Imported {os.path.basename(file)}")

    def export_episode_csv(self):
        content = self.csv_preview_text.get(1.0, tk.END).strip()
        if not content:
            messagebox.showwarning("Nothing to export", "No CSV content to export!")
            return
        lists_dir = os.path.join(APP_DIR, "episode_lists")
        os.makedirs(lists_dir, exist_ok=True)
        show = self.show_name_var.get().strip().lower().replace(" ", "_")
        default_name = f"{show}_episodes.csv" if show else "episode_list.csv"
        file = filedialog.asksaveasfilename(title="Export Episode CSV", initialdir=lists_dir,
                                            defaultextension=".csv", initialfile=default_name,
                                            filetypes=[("CSV files", "*.csv")])
        if not file:
            return
        try:
            with open(file, "w", encoding="utf-8", newline="") as f:
                f.write(content + "\n")
            self.update_status(f"Exported to {os.path.basename(file)}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export: {e}")

    def load_csv_to_main(self):
        content = self.csv_preview_text.get(1.0, tk.END).strip()
        if not content:
            messagebox.showwarning("Nothing to load", "No CSV content to load!")
            return
        lists_dir = os.path.join(APP_DIR, "episode_lists")
        os.makedirs(lists_dir, exist_ok=True)
        show = self.show_name_var.get().strip().lower().replace(" ", "_")
        name = f"{show}_episodes.csv" if show else \
            f"pasted_episodes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path = os.path.join(lists_dir, name)
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(content + "\n")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save CSV: {e}")
            return
        self.episode_csv.set(path)
        self.notebook.select(0)
        self.update_status(f"Loaded {os.path.basename(path)} into the Process tab.")


def main():
    root = tk.Tk()
    app = VideoSplitterGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
