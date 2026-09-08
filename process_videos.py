"""
process_videos.py - Scene Segment Splitter core engine

A single, reliable engine used by BOTH the CLI (scene_splitter.py --cli) and the
GUI (video_processor_gui.py / gui.py). It:

  * loads an episode list (tolerant of malformed / unquoted CSVs),
  * parses show / season / episode(s) / titles out of the filename,
  * detects inter-episode transitions (long fades to black, with fallbacks),
  * splits the source into per-episode files without re-encoding (mkvmerge),
  * re-inserts the shared intro at the start of every segment after the first.

Design notes
------------
Inter-episode boundaries are LONG fades (typically 3-6s), while act/commercial
breaks are short (~0.3-1.5s). The detector therefore scores candidates by black
duration (longer = better) and proximity to the expected boundary, instead of
filtering long fades out. The expected boundary for an N-segment file is derived
from the runtime:  boundary_j = intro + j * (duration - intro) / N.
For the common two-episode case this is  (duration + intro) / 2 .
"""

import os
import re
import sys
import csv
import json
import shutil
import logging
import platform
import tempfile
import unicodedata
import subprocess
from io import StringIO
from pathlib import Path
from datetime import datetime
from difflib import SequenceMatcher
from typing import List, Tuple, Optional, Dict

# Directory this module lives in - used to resolve bundled binaries, the default
# episode list and relative config paths regardless of the current directory.
APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Release-metadata / quality tags that may appear in a filename but never in a
# real episode title. Stripped (case-insensitively) before matching. Only clear
# technical tokens are listed - ambiguous English words (e.g. "proper",
# "internal") are deliberately excluded so real titles are never corrupted.
_TAG_PATTERN = re.compile(
    r'\b('
    r'\d{3,4}p|x26[45]|h\.?26[45]|hevc|xvid|divx|'
    r'web-?dl|web-?rip|bluray|blu-ray|bdrip|brrip|dvdrip|hdtv|amzn|dsnp|hmax|'
    r'aac\d?|ac3|dd5\.1|ddp5\.1|flac|10bit|remux|repack'
    r')\b',
    re.IGNORECASE,
)
# A trailing release-group tag in brackets, e.g. "[GROUP]" or "{grp}". Kept
# strict (bracketed only) so legitimate hyphenated titles such as
# "The Ed-touchables" or "Mission Ed-Possible" are never truncated.
_GROUP_PATTERN = re.compile(r'\s*[\[\{][^\]\}]{1,40}[\]\}]\s*$')

# Candidate separators between two (or more) episode titles in a filename.
# Order matters: multi-character separators are tried before single characters.
_SEGMENT_SEPARATORS = [' + ', '+', ' & ', ' and ', ' / ', ' _ ', '_']


def setup_logging(log_dir: str = "logs") -> str:
    """Configure logging to a timestamped file (under log_dir) and stdout."""
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(log_dir, f"video_processing_{timestamp}.log")
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s',
        handlers=[
            logging.FileHandler(log_filename, encoding='utf-8'),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return log_filename


class VideoProcessor:
    SUPPORTED_FORMATS = ('.mkv', '.mp4', '.avi', '.m4v', '.mov')
    INTRO_DURATION = 47  # seconds; overridden per-show via config

    def __init__(self, input_folder: str, output_folder: str,
                 config: Optional[dict] = None, progress_callback=None):
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.progress_callback = progress_callback
        self.cancel_requested = False
        self.temp_folder: Optional[str] = None

        # Resolve binaries once (bundled bin/ first, then system PATH).
        self.ffmpeg_path = self._get_binary_path('ffmpeg')
        self.ffprobe_path = self._get_binary_path('ffprobe')
        self.mkvmerge_path = self._get_binary_path('mkvmerge')

        os.makedirs(output_folder, exist_ok=True)

        # Config-driven parameters (with sensible defaults).
        self.episode_map: Dict[str, List[dict]] = {}
        self._episode_by_number: Dict[Tuple[int, int], dict] = {}
        self.apply_config(config or {})

        # If the config did not supply a valid episode list, fall back to the
        # bundled default so the tool still runs out of the box.
        if not self.episode_map:
            default_csv = os.path.join(APP_DIR, "episode_list.csv")
            if os.path.exists(default_csv):
                self._set_episode_list(default_csv)

    # ------------------------------------------------------------------ config
    def apply_config(self, config: dict) -> None:
        self.INTRO_DURATION = int(config.get('intro_duration', self.INTRO_DURATION))
        # auto_target: derive the expected boundary from runtime. Defaults to
        # True unless a legacy config pins an explicit target_time.
        self.auto_target = bool(config.get('auto_target', 'target_time' not in config))
        self.target_time = float(config.get('target_time', 710))
        self.time_margin = float(config.get('time_margin', 120))
        self.black_duration = str(config.get('black_duration', "0.2"))
        self.pixel_threshold = str(config.get('pixel_threshold', "0.15"))
        self.picture_threshold = str(config.get('picture_threshold', "0.95"))
        # "Smart" (duration/proximity scoring) is the robust default; the two
        # positional modes are kept for backward compatibility with old configs.
        self.transition_selection = config.get('transition_selection', "Smart")
        self.split_point = config.get('split_point', "At Start of Fade")
        self.detection_method = config.get('detection_method', "Comprehensive (All Methods)")
        # What to do when no boundary can be found: copy the source through
        # unsplit (safe default), split at the derived midpoint, or skip.
        self.on_detection_failure = config.get('on_detection_failure', "copy")

        episode_csv = config.get('episode_csv')
        if episode_csv:
            resolved = self._resolve_path(episode_csv)
            if os.path.exists(resolved):
                self._set_episode_list(resolved)
            else:
                logging.warning(f"Configured episode_csv not found: {episode_csv} "
                                f"(resolved: {resolved}); keeping current episode list.")

    def _resolve_path(self, path: str) -> str:
        """Resolve a possibly-relative path against CWD then the app directory."""
        if os.path.isabs(path):
            return path
        if os.path.exists(path):
            return os.path.abspath(path)
        candidate = os.path.join(APP_DIR, path)
        return candidate if os.path.exists(candidate) else path

    # ------------------------------------------------------------- progress/log
    def _progress(self, message: str, percentage: Optional[float] = None) -> None:
        """Emit a progress message (to the log) and an optional percentage
        (to the GUI callback). Safe to call from the base/CLI too."""
        if message:
            logging.info(message)
        if self.progress_callback and percentage is not None:
            self.progress_callback(None, percentage)

    def set_progress_callback(self, callback) -> None:
        self.progress_callback = callback

    def cancel_processing(self) -> None:
        self.cancel_requested = True
        self._progress("Cancellation requested...")

    # -------------------------------------------------------------- binaries
    def _get_binary_path(self, binary_name: str) -> str:
        """Locate a helper binary: bundled bin/ first, then the system PATH."""
        ext = '.exe' if platform.system().lower() == 'windows' else ''
        bundled = os.path.join(APP_DIR, 'bin', binary_name + ext)
        if os.path.exists(bundled):
            return bundled
        on_path = shutil.which(binary_name)
        if on_path:
            return on_path
        raise FileNotFoundError(
            f"'{binary_name}' not found. It is normally downloaded automatically "
            f"on first launch; if that failed, place {binary_name}{ext} in the "
            f"'bin' folder or install it and add it to your PATH."
        )

    # --------------------------------------------------------- episode list
    def _set_episode_list(self, path: str) -> None:
        self.episode_map, self._episode_by_number = self._load_episode_list(path)

    def _load_episode_list(self, episode_list_path: str) -> Tuple[Dict[str, List[dict]], Dict[Tuple[int, int], dict]]:
        """Load an episode list into (title_map, number_map).

        title_map maps a normalized title to the LIST of episodes bearing that
        title (duplicate titles - reruns, same-season repeats - are common), so
        lookups can disambiguate rather than silently overwrite.

        Tolerant of malformed rows: rows with unquoted commas in the title (a
        very common defect in scraped lists) are reconstructed by treating the
        first two columns as season/episode, the last column as the SxxExx code,
        and *everything in between* as the title.
        """
        by_title: Dict[str, List[dict]] = {}
        by_number: Dict[Tuple[int, int], dict] = {}
        malformed = 0
        try:
            with open(episode_list_path, 'r', encoding='utf-8-sig', newline='') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if not header:
                    logging.warning(f"Episode list is empty: {episode_list_path}")
                    return by_title, by_number
                for row in reader:
                    if not row or all(not c.strip() for c in row):
                        continue
                    parsed = self._parse_csv_row(row)
                    if not parsed:
                        malformed += 1
                        continue
                    season, episode, name = parsed
                    if len(row) > 4:
                        malformed += 1  # had unquoted commas; reconstructed
                    info = {'season': season, 'episode': episode, 'full_name': name}
                    # Key with the SAME transform used at lookup time so a clean
                    # title matches regardless of release tags on either side.
                    key = self._normalize_title(self._strip_tags(name))
                    by_title.setdefault(key, []).append(info)
                    by_number[(season, episode)] = info
        except Exception as e:
            logging.error(f"Error loading episode list '{episode_list_path}': {e}")
            return {}, {}

        logging.info(f"Loaded {len(by_number)} episodes from {os.path.basename(episode_list_path)}"
                     + (f" ({malformed} row(s) reconstructed/skipped)" if malformed else ""))
        return by_title, by_number

    @staticmethod
    def _parse_csv_row(row: List[str]) -> Optional[Tuple[int, int, str]]:
        """Return (season, episode, name) from a CSV row, reconstructing the
        title if unquoted commas split it across extra columns."""
        cells = [c.strip() for c in row]
        if len(cells) < 3:
            return None
        try:
            season = int(cells[0])
            episode = int(cells[1])
        except (ValueError, IndexError):
            return None
        if len(cells) == 3:
            name = cells[2]
        else:
            # Columns 2..n: the title plus a trailing SxxExx code (AbbvCombo).
            tail = cells[2:]
            if re.fullmatch(r'S\d{1,2}E\d{1,3}', tail[-1], re.IGNORECASE):
                tail = tail[:-1]
            name = ", ".join(t for t in tail if t)
        return (season, episode, name.strip()) if name.strip() else None

    # -------------------------------------------------------- normalization
    def _normalize_title(self, title: str) -> str:
        """Normalize a title for matching: fold accents, expand common symbols,
        drop punctuation, collapse whitespace."""
        # Fold accents/diacritics to ASCII so "à la Mode" == "a la Mode".
        working = unicodedata.normalize('NFKD', title)
        working = ''.join(c for c in working if not unicodedata.combining(c))

        replacements = {
            r'Mr\.': 'Mr', r'Mrs\.': 'Mrs', r'Ms\.': 'Ms', r'Dr\.': 'Dr',
            r'Jr\.': 'Jr', r'Sr\.': 'Sr', r'St\.': 'St', r'vs\.': 'vs',
            r'\.\.\.': ' ',
            r'\s*&\s*': ' and ',
            r'\s*\+\s*': ' and ',
            r'\s*♥\s*': ' heart ',   # ♥
            r'(\w)-(\w)': r'\1\2',
        }
        for pattern, repl in replacements.items():
            working = re.sub(pattern, repl, working)

        working = working.lower()
        working = re.sub(r'[^\w\s]', '', working)
        working = re.sub(r'\s+', ' ', working).strip()
        return working

    @staticmethod
    def _strip_tags(text: str) -> str:
        """Remove release/quality metadata and a trailing group tag."""
        text = _TAG_PATTERN.sub(' ', text)
        text = _GROUP_PATTERN.sub('', text)
        return re.sub(r'\s+', ' ', text).strip()

    def _sanitize_filename(self, filename: str) -> str:
        filename = filename.replace('?', '')
        return re.sub(r'[<>:"/\\|*]', '_', filename)

    # ----------------------------------------------------- filename parsing
    def _get_episode_info(self, filename: str) -> Tuple[Optional[str], Optional[int], Optional[List[int]], Optional[str]]:
        """Parse 'Show - SxxE.. - Title[+Title...]' from a filename.

        Accepts multi-episode encodings: S01E15-16, S01E15-E16, S01E01E02.
        Returns (show_name, season, [episode_numbers], remainder).
        """
        stem = os.path.splitext(filename)[0]
        # show - S<season>E<ep>[range/extra eps] - <remainder>
        pattern = (r'^(?P<show>.+?)\s*-\s*'
                   r'S(?P<season>\d{1,2})'
                   r'E(?P<ep>\d{1,3})'
                   r'(?P<extra>(?:\s*-\s*E?\d{1,3}|E\d{1,3})*)'
                   r'\s*-\s*(?P<rest>.+)$')
        match = re.match(pattern, stem, re.IGNORECASE)
        if not match:
            return None, None, None, None
        show = match.group('show').strip()
        season = int(match.group('season'))
        episodes = [int(match.group('ep'))]
        for extra in re.findall(r'\d{1,3}', match.group('extra') or ''):
            episodes.append(int(extra))
        remainder = match.group('rest').strip()
        return show, season, episodes, remainder

    def _split_segments(self, remainder: str, season: Optional[int]) -> List[str]:
        """Split the title remainder into per-episode titles.

        CSV-guided: a separator is only accepted when *every* resulting part
        matches an episode in the map (so 'Arnold & Lila' stays one title but
        'Dog Gone & All You Cant Eat' splits correctly). Falls back to a plain
        '+' split, then to a single title.
        """
        remainder = self._strip_tags(remainder)

        best: Optional[List[str]] = None
        for sep in _SEGMENT_SEPARATORS:
            if sep not in remainder:
                continue
            parts = [p.strip() for p in remainder.split(sep) if p.strip()]
            if len(parts) < 2:
                continue
            if self.episode_map and all(self._find_matching_episode(p, season) for p in parts):
                if best is None or len(parts) > len(best):
                    best = parts
        if best:
            return best

        # Fallback: literal '+' (the repo's historical convention).
        if '+' in remainder:
            parts = [p.strip() for p in remainder.split('+') if p.strip()]
            if len(parts) >= 2:
                return parts
        return [remainder.strip()] if remainder.strip() else []

    @staticmethod
    def _pick_from(cands: List[dict], season: Optional[int],
                   number: Optional[int]) -> Optional[dict]:
        """Disambiguate when a title matches several episodes: prefer the
        filename's (season, number), then the same season, then the first."""
        if not cands:
            return None
        if len(cands) == 1:
            return cands[0]
        if season is not None and number is not None:
            for c in cands:
                if c['season'] == season and c['episode'] == number:
                    return c
        if season is not None:
            same = [c for c in cands if c['season'] == season]
            if same:
                return same[0]
        return cands[0]

    def _find_matching_episode(self, episode_name: str,
                               season: Optional[int] = None,
                               number: Optional[int] = None) -> Optional[dict]:
        """Find the episode that best matches a title.

        Prefers an exact normalized match, then a season-scoped fuzzy match that
        clears 0.75 AND beats the runner-up by a margin. Duplicate titles are
        disambiguated via (season, number) - see _pick_from.
        """
        if not episode_name:
            return None
        search = self._normalize_title(self._strip_tags(episode_name))
        if not search:
            return None

        # Exact normalized match (season-scoped first).
        cands = self.episode_map.get(search)
        if cands:
            scoped = [c for c in cands if season is None or c['season'] == season]
            return self._pick_from(scoped or cands, season, number)

        # Fuzzy match: return the best key clearing the threshold + margin.
        def best_key(keys):
            scored = sorted(((SequenceMatcher(None, search, k).ratio(), k) for k in keys),
                            key=lambda x: x[0], reverse=True)
            if not scored:
                return None
            top_ratio, top_key = scored[0]
            second = scored[1][0] if len(scored) > 1 else 0.0
            if top_ratio >= 0.90 or (top_ratio > 0.75 and (top_ratio - second) >= 0.03):
                return top_key
            return None

        if season is not None:
            scoped_keys = [k for k, lst in self.episode_map.items()
                           if any(i['season'] == season for i in lst)]
            k = best_key(scoped_keys)
            if k:
                same = [c for c in self.episode_map[k] if c['season'] == season]
                return self._pick_from(same or self.episode_map[k], season, number)
        k = best_key(list(self.episode_map.keys()))
        return self._pick_from(self.episode_map[k], season, number) if k else None

    def _lookup_episode(self, season: int, number: int,
                        title: Optional[str]) -> Optional[dict]:
        """Resolve a segment to its authoritative episode entry.

        The TITLE is authoritative here: this tool exists to *correct* episode
        numbering, and source filenames routinely carry the wrong number (e.g. a
        file named 'S01E17-18 - Fool On the Ed + A Boy and His Ed' whose titles
        are actually S01E15/E16 in the list). So match by title first (using the
        filename number only to disambiguate duplicate titles), and fall back to
        the filename's (season, number) when no title matches.
        """
        if title:
            info = self._find_matching_episode(title, season, number)
            if info:
                return info
        return self._episode_by_number.get((season, number))

    # ------------------------------------------------------------ time utils
    def _time_to_seconds(self, time_str: str) -> float:
        h, m, s = time_str.split(':')
        return float(h) * 3600 + float(m) * 60 + float(s)

    def _seconds_to_time(self, seconds: float) -> str:
        seconds = max(0.0, float(seconds))
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:06.3f}"

    def get_video_duration(self, video_path: str) -> Optional[float]:
        try:
            cmd = [self.ffprobe_path, "-v", "quiet", "-print_format", "json",
                   "-show_format", str(Path(video_path).resolve())]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logging.error(f"ffprobe error: {result.stderr}")
                return None
            return float(json.loads(result.stdout)['format']['duration'])
        except Exception as e:
            logging.error(f"Error getting video duration: {e}")
            return None

    # --------------------------------------------------------- detection
    def _run_blackdetect(self, video_path: str,
                         d: str, pix: str, pic: str) -> List[Tuple[float, float, float]]:
        """Return all (start, end, duration) black intervals in the whole file."""
        cmd = [self.ffmpeg_path, "-i", str(Path(video_path).resolve()),
               "-vf", f"blackdetect=d={d}:pix_th={pix}:pic_th={pic}",
               "-an", "-f", "null", "-"]
        blacks: List[Tuple[float, float, float]] = []
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
        except Exception as e:
            self._progress(f"blackdetect failed: {e}")
            return blacks
        for line in result.stderr.split('\n'):
            if "black_start:" in line:
                try:
                    start = float(line.split("black_start:")[1].split()[0])
                    end = float(line.split("black_end:")[1].split()[0])
                    dur = float(line.split("black_duration:")[1].split()[0])
                    blacks.append((start, end, dur))
                except (IndexError, ValueError):
                    continue
        return blacks

    def _detect_black_intervals(self, video_path: str,
                                targets: Optional[List[float]] = None) -> List[Tuple[float, float, float]]:
        """Blackdetect with a threshold ladder. Relaxes settings until a black
        interval lands within time_margin of a target (not merely until *some*
        black is found - unrelated act breaks must not stop the ladder)."""
        ladder = [
            (self.black_duration, self.pixel_threshold, self.picture_threshold),
            ("0.1", "0.20", "0.92"),
            ("0.05", "0.30", "0.85"),
        ]
        best: List[Tuple[float, float, float]] = []
        seen = set()
        for i, (d, pix, pic) in enumerate(ladder):
            if (d, pix, pic) in seen:
                continue
            seen.add((d, pix, pic))
            blacks = self._run_blackdetect(video_path, d, pix, pic)
            if not blacks:
                continue
            best = blacks
            in_window = targets is None or any(
                any(abs(b[0] - t) <= self.time_margin for b in blacks) for t in targets)
            if in_window:
                if i > 0:
                    self._progress(f"  (used relaxed thresholds d={d} pix={pix} pic={pic})")
                return blacks
        return best

    def _expected_boundaries(self, duration: float, num_segments: int) -> List[float]:
        """Expected boundary time(s). For an N-segment file the shared intro is
        only at the very start, so body length = (duration - intro)/N and the
        j-th boundary is intro + j*body_len."""
        if self.auto_target or num_segments != 2:
            body = max(1.0, (duration - self.INTRO_DURATION) / num_segments)
            return [self.INTRO_DURATION + j * body for j in range(1, num_segments)]
        # Legacy explicit target (two-segment only).
        return [self.target_time]

    def _pick_candidate(self, blacks: List[Tuple[float, float, float]],
                        target: float, allow_hard_cut: bool = False) -> Optional[Tuple[float, float, float]]:
        """Choose the best black interval near `target`.

        Zero-duration entries are hard cuts (from scene-change detection) and are
        NOT treated as real inter-episode fades unless allow_hard_cut is set, so
        dense hard cuts can never silently masquerade as a boundary.
        """
        window = [b for b in blacks if abs(b[0] - target) <= self.time_margin]
        if not allow_hard_cut:
            window = [b for b in window if b[2] > 0.0]
        if not window:
            return None

        if self.transition_selection == "Select Earliest Transition":
            return min(window, key=lambda b: b[0])
        if self.transition_selection == "Select Latest Transition":
            return max(window, key=lambda b: b[0])

        # Smart: prefer long fades close to the target. Duration dominates,
        # proximity breaks ties. (cap keeps end-credits fades from dominating.)
        margin = max(self.time_margin, 1.0)
        def score(b):
            start, _end, dur = b
            return min(dur, 8.0) - 1.5 * (abs(start - target) / margin)
        return max(window, key=score)

    def detect_boundaries(self, video_path: str, duration: float,
                          num_segments: int = 2) -> List[Tuple[float, float, float]]:
        """Detect the num_segments-1 inter-episode boundaries.

        Comprehensive tries blackdetect (threshold ladder) then a luminance
        fallback for faint fades. If no real fade is found near a target it
        returns fewer boundaries than requested, so the caller's
        on_detection_failure policy (copy/midpoint/skip) takes over rather than
        splitting at an arbitrary point. Scene-change (hard-cut) detection is
        only used when explicitly selected.
        """
        if num_segments < 2:
            return []
        self._progress("Analyzing video for episode transitions...")

        method = self.detection_method
        targets = self._expected_boundaries(duration, num_segments)

        if method == "Histogram Analysis":
            chosen = self._choose_boundaries(self._detect_via_histogram(video_path, duration), targets)
        elif method == "Scene Change Detection":
            cuts = self._detect_via_scene_change(video_path, duration)
            chosen = self._choose_boundaries(cuts, targets, allow_hard_cut=True)
        else:  # Standard Blackdetect Only / Comprehensive
            blacks = self._detect_black_intervals(video_path, targets)
            chosen = self._choose_boundaries(blacks, targets)
            if len(chosen) < len(targets) and method == "Comprehensive (All Methods)":
                self._progress("No clean fade near a boundary; trying luminance analysis...")
                hist = self._detect_via_histogram(video_path, duration)
                chosen = self._choose_boundaries(blacks + hist, targets)

        for b in chosen:
            kind = "hard cut" if b[2] <= 0.0 else f"fade {b[2]:.2f}s"
            self._progress(f"  Boundary at {self._seconds_to_time(b[0])} ({kind})")
        return chosen

    def _choose_boundaries(self, blacks: List[Tuple[float, float, float]],
                           targets: List[float],
                           allow_hard_cut: bool = False) -> List[Tuple[float, float, float]]:
        """Pick one distinct candidate per expected boundary target."""
        chosen: List[Tuple[float, float, float]] = []
        used: set = set()
        for target in targets:
            pick = self._pick_candidate(
                [b for b in blacks if b[0] not in used], target, allow_hard_cut)
            if pick:
                used.add(pick[0])
                chosen.append(pick)
        chosen.sort(key=lambda b: b[0])
        return chosen

    def _detect_via_histogram(self, video_path: str,
                              duration: float) -> List[Tuple[float, float, float]]:
        """Luminance-based black detection (fallback for faint fades).

        Uses signalstats+metadata=print and parses lavfi.signalstats.YAVG.
        """
        self._progress("Running luminance (signalstats) analysis...")
        fps = 10
        cmd = [self.ffmpeg_path, "-i", str(Path(video_path).resolve()),
               "-vf", f"fps={fps},signalstats,metadata=print", "-f", "null", "-"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
        except Exception as e:
            self._progress(f"Luminance analysis failed: {e}")
            return []

        blacks: List[Tuple[float, float, float]] = []
        black_start: Optional[float] = None
        cur_time = 0.0
        min_dur = float(self.black_duration or 0.2)
        for line in result.stderr.split('\n'):
            tmatch = re.search(r'pts_time:(\d+\.?\d*)', line)
            if tmatch:
                cur_time = float(tmatch.group(1))
                continue
            ymatch = re.search(r'lavfi\.signalstats\.YAVG=(\d+\.?\d*)', line)
            if ymatch:
                yavg = float(ymatch.group(1))
                if yavg < 16:  # near-black (0-255 scale)
                    if black_start is None:
                        black_start = cur_time
                elif black_start is not None:
                    dur = cur_time - black_start
                    if dur >= min_dur:
                        blacks.append((black_start, cur_time, dur))
                    black_start = None
        if black_start is not None:
            dur = cur_time - black_start
            if dur >= min_dur:
                blacks.append((black_start, cur_time, dur))
        return blacks

    def _detect_via_scene_change(self, video_path: str,
                                 duration: float) -> List[Tuple[float, float, float]]:
        """Scene-change detection for hard cuts (no fade). Kept as candidates
        regardless of adjacent blackness."""
        self._progress("Running scene-change detection...")
        cmd = [self.ffmpeg_path, "-i", str(Path(video_path).resolve()),
               "-vf", "select='gt(scene,0.4)',metadata=print", "-f", "null", "-"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
        except Exception as e:
            self._progress(f"Scene-change detection failed: {e}")
            return []
        cuts: List[Tuple[float, float, float]] = []
        for line in result.stderr.split('\n'):
            tmatch = re.search(r'pts_time:(\d+\.?\d*)', line)
            if tmatch:
                t = float(tmatch.group(1))
                # A hard cut has no measurable fade; treat as a zero-length mark.
                cuts.append((t, t, 0.0))
        return cuts

    # --------------------------------------------------------- splitting
    def _extract_part(self, video_path: str, start: str, end: str, out_file: str) -> bool:
        """Extract [start, end] into out_file with mkvmerge (no re-encode)."""
        cmd = [self.mkvmerge_path, "--output", str(Path(out_file).resolve()),
               "--split", f"parts:{start}-{end}", str(Path(video_path).resolve())]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode not in (0, 1):  # 1 = warnings, output still made
            logging.error(f"mkvmerge error: {result.stderr}")
            return False
        return self._resolve_split_output(out_file) is not None

    @staticmethod
    def _resolve_split_output(out_file: str) -> Optional[str]:
        """mkvmerge may name a single-part output exactly, or suffix it -001."""
        p = Path(out_file)
        if p.exists():
            return str(p)
        numbered = p.with_name(f"{p.stem}-001{p.suffix}")
        return str(numbered) if numbered.exists() else None

    def _unique_output(self, output_file: str) -> str:
        """Avoid silently overwriting an existing output file."""
        if not os.path.exists(output_file):
            return output_file
        base, ext = os.path.splitext(output_file)
        i = 2
        while os.path.exists(f"{base} ({i}){ext}"):
            i += 1
        return f"{base} ({i}){ext}"

    def split_video(self, video_path: str,
                    segments: List[Tuple[float, float, dict, bool]]) -> int:
        """Write each segment. `segments` = list of
        (start_sec, end_sec, episode_info_or_None, prepend_intro). Returns the
        number of segments written."""
        input_ext = os.path.splitext(video_path)[1].lower()
        if input_ext not in ('.mkv',):
            input_ext = '.mkv'  # mkvmerge always outputs matroska
        show_name = self._current_show or "Show"
        season = self._current_season or 1
        written = 0

        for i, (start, end, info, prepend_intro) in enumerate(segments, 1):
            if self.cancel_requested:
                break
            if info:
                out_name = (f"{show_name} - S{info['season']:02d}E{info['episode']:02d} "
                            f"- {info['full_name']}{input_ext}")
            else:
                ep_num = (self._current_episodes[i - 1]
                          if self._current_episodes and i - 1 < len(self._current_episodes)
                          else i)
                out_name = f"{show_name} - S{season:02d}E{ep_num:02d} - Part {i}{input_ext}"
            output_file = self._unique_output(
                os.path.join(self.output_folder, self._sanitize_filename(out_name)))

            start_s = self._seconds_to_time(start)
            end_s = self._seconds_to_time(end)
            temp_out = os.path.join(self.temp_folder, f"seg_{i}.mkv")

            if prepend_intro and self.INTRO_DURATION > 0:
                intro_file = os.path.join(self.temp_folder, f"intro_{i}.mkv")
                body_file = os.path.join(self.temp_folder, f"body_{i}.mkv")
                if not self._extract_part(video_path, "00:00:00.000",
                                          self._seconds_to_time(self.INTRO_DURATION), intro_file):
                    logging.error(f"Segment {i}: failed to extract intro."); continue
                if not self._extract_part(video_path, start_s, end_s, body_file):
                    logging.error(f"Segment {i}: failed to extract body."); continue
                concat = [self.mkvmerge_path, "--output", str(Path(temp_out).resolve()),
                          str(Path(self._resolve_split_output(intro_file)).resolve()),
                          '+', str(Path(self._resolve_split_output(body_file)).resolve())]
                res = subprocess.run(concat, capture_output=True, text=True)
                if res.returncode not in (0, 1):
                    logging.error(f"Segment {i}: concat failed: {res.stderr}"); continue
            else:
                if not self._extract_part(video_path, start_s, end_s, temp_out):
                    logging.error(f"Segment {i}: extraction failed."); continue

            produced = self._resolve_split_output(temp_out)
            if not produced:
                logging.error(f"Segment {i}: output not produced."); continue
            shutil.move(produced, output_file)
            self._progress(f"Saved: {os.path.basename(output_file)}")
            written += 1
        return written

    # ------------------------------------------------------------- orchestrate
    def process_videos(self) -> None:
        try:
            files = sorted(f for f in os.listdir(self.input_folder)
                           if f.lower().endswith(self.SUPPORTED_FORMATS))
        except FileNotFoundError:
            self._progress(f"Input folder not found: {self.input_folder}")
            return
        if not files:
            self._progress(f"No supported video files found in {self.input_folder}. "
                           f"Supported: {', '.join(self.SUPPORTED_FORMATS)}")
            return

        total = len(files)
        for index, file in enumerate(files):
            if self.cancel_requested:
                break
            self._progress(f"\n--- Processing {index + 1}/{total}: {file} ---",
                           (index / total) * 100)
            self.temp_folder = tempfile.mkdtemp(prefix="sss_")
            try:
                self._process_one(file)
            except Exception as e:
                logging.error(f"Error processing {file}: {e}", exc_info=True)
            finally:
                shutil.rmtree(self.temp_folder, ignore_errors=True)
                self.temp_folder = None

        status = "Processing stopped." if self.cancel_requested else "All videos processed!"
        self._progress(status, 100)

    def _process_one(self, file: str) -> None:
        src_path = os.path.join(self.input_folder, file)
        show_name, season, episodes, remainder = self._get_episode_info(file)
        if not show_name or season is None:
            self._progress(f"WARNING: Could not parse 'Show - SxxExx - Title' from "
                           f"'{file}'. Skipping.")
            return

        titles = self._split_segments(remainder, season)
        num_segments = max(len(titles), len(episodes)) if (titles or episodes) else 1

        self._current_show = show_name
        self._current_season = season
        self._current_episodes = episodes

        # Single-episode file: copy through, named from the CSV when matched.
        # (No remux needed - a straight copy preserves the original container.)
        if num_segments < 2:
            title = titles[0] if titles else remainder
            info = self._lookup_episode(season, episodes[0], title)
            if info:
                out_name = (f"{show_name} - S{season:02d}E{info['episode']:02d} "
                            f"- {info['full_name']}{os.path.splitext(file)[1]}")
            else:
                self._progress(f"NOTE: No episode-list match for '{title}'; "
                               f"copying with original name.")
                out_name = file
            dest = self._unique_output(
                os.path.join(self.output_folder, self._sanitize_filename(out_name)))
            shutil.copy2(src_path, dest)
            self._progress(f"Single episode -> {os.path.basename(dest)}")
            return

        # Multi-episode: convert to MKV (copy, no re-encode) so mkvmerge can
        # split precisely. Only done for files that will actually be split.
        video_path = src_path
        if not file.lower().endswith('.mkv'):
            mkv_path = os.path.join(self.temp_folder, os.path.splitext(file)[0] + '.mkv')
            if not self.convert_to_mkv(src_path, mkv_path):
                self._progress(f"WARNING: Could not convert {file} to MKV. Skipping.")
                return
            video_path = mkv_path

        duration = self.get_video_duration(video_path)
        if not duration:
            self._progress(f"WARNING: Could not read duration of {file}. Skipping.")
            return
        self._progress(f"Duration: {self._seconds_to_time(duration)} "
                       f"({duration/60:.1f} min); expecting {num_segments} episodes.")

        boundaries = self.detect_boundaries(video_path, duration, num_segments)

        if len(boundaries) < num_segments - 1:
            self._handle_detection_failure(src_path, video_path, file, duration,
                                           num_segments, len(boundaries),
                                           titles, episodes, season)
            return

        segments = self._build_segments(boundaries, duration, titles, episodes, season)
        n = self.split_video(video_path, segments)
        self._progress(f"Done: wrote {n} file(s) for {file}.")

    def _build_segments(self, boundaries, duration, titles, episodes, season):
        """Turn boundary times into (start, end, info, prepend_intro) segments."""
        cut_starts = [0.0]
        cut_ends = []
        for b in boundaries:
            start, end, _ = b
            cut_ends.append(start)  # previous episode always ends at fade start
            if self.split_point == "After Fade":
                cut_starts.append(end)   # drop the fade
            else:  # "At Start of Fade"
                cut_starts.append(start)
        cut_ends.append(duration)

        segments = []
        for i in range(len(cut_starts)):
            title = titles[i] if i < len(titles) else None
            ep_num = episodes[i] if i < len(episodes) else None
            info = None
            if ep_num is not None:
                info = self._lookup_episode(season, ep_num, title)
            elif title:
                info = self._find_matching_episode(title, season)
            segments.append((cut_starts[i], cut_ends[i], info, i > 0))
        return segments

    def _handle_detection_failure(self, src_path, video_path, file, duration,
                                  num_segments, found, titles, episodes, season):
        mode = self.on_detection_failure
        self._progress(f"WARNING: Found only {found} of {num_segments - 1} "
                       f"transition(s) for {file}.")
        if mode == "midpoint":
            self._progress("Falling back to a derived-midpoint split.")
            targets = self._expected_boundaries(duration, num_segments)
            fake = [(t, t, 0.0) for t in targets]
            segments = self._build_segments(fake, duration, titles, episodes, season)
            n = self.split_video(video_path, segments)
            self._progress(f"Midpoint fallback wrote {n} file(s).")
        elif mode == "skip":
            self._progress("Skipping (on_detection_failure=skip).")
        else:  # "copy"
            dest = self._unique_output(os.path.join(self.output_folder, file))
            shutil.copy2(src_path, dest)
            self._progress(f"Copied source unsplit -> {os.path.basename(dest)} "
                           f"(no reliable boundary found).")

    def convert_to_mkv(self, input_video: str, output_video: str) -> bool:
        cmd = [self.ffmpeg_path, "-i", str(Path(input_video).resolve()),
               "-c", "copy", "-sn", "-y", str(Path(output_video).resolve())]
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            return True
        except subprocess.CalledProcessError as e:
            logging.error(f"Error converting to MKV: {e.stderr}")
            return False

    # Attributes populated per-file during processing.
    _current_show: Optional[str] = None
    _current_season: Optional[int] = None
    _current_episodes: Optional[List[int]] = None


if __name__ == "__main__":
    log_file = setup_logging()
    logging.info(f"Starting video processing at {datetime.now()}")
    logging.info(f"Log file: {log_file}")
    processor = VideoProcessor("input_videos", "output_videos")
    processor.process_videos()
    logging.info(f"Processing completed at {datetime.now()}")
