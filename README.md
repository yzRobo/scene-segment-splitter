# Scene Segment Splitter

Split video files that contain **two (or more) episodes** into correctly named,
per-episode files - without re-encoding - and re-insert the shared intro at the
start of every episode after the first.

Originally built for classic Nickelodeon / Cartoon Network cartoons (Hey Arnold!,
Ed Edd n Eddy, Rugrats, etc.) where a single "half-hour" file holds two ~11-minute
segments joined by a fade to black.

---

## Contents
- [How it works](#how-it-works)
- [What's new in this release](#whats-new-in-this-release)
- [Requirements](#requirements)
- [Setup](#setup)
- [FFmpeg / mkvmerge binaries](#ffmpeg--mkvmerge-binaries)
- [Usage (GUI)](#usage-gui)
- [Usage (CLI)](#usage-cli)
- [Episode lists](#episode-lists)
- [Configuration reference](#configuration-reference)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## How it works

1. **Parse the filename** - `Show Name - S01E15-16 - Title A + Title B` - to get the
 show, season, source episode number(s) and the per-segment titles.
2. **Detect the boundary** - scan the whole file for black frames and pick the
 long fade nearest the expected midpoint. Inter-episode boundaries are *long*
 fades (typically 3-6 s); short act-break fades are ignored. The expected
 boundary is derived from the runtime: `(duration + intro) / 2` for a two-episode
 file (generalized to `intro + j*(duration-intro)/N` for N segments).
3. **Look up the real episode** by **title** in your episode-list CSV. Source
 files often carry the *wrong* episode number, so the title is authoritative - 
 the tool corrects the numbering and names each output from the list.
4. **Split losslessly** with `mkvmerge` and prepend the intro to later segments.

The result: `Show Name - S01E21 - Who, What, Where, Ed!.mkv` and
`Show Name - S01E22 - Keeping Up with the Eds.mkv`.

## What's new in this release

- **Reliable across shows.** The old build effectively only worked on Hey Arnold.
 Fixed: episode-list CSVs with unquoted commas silently truncated titles; the
 black-frame duration cap discarded the real (long) inter-episode fade; the
 target time was a hard-coded per-show constant; the histogram and scene-change
 detectors were non-functional.
- **Auto-detected boundary** from the runtime - no per-show tuning needed.
- **Smart transition scoring** (favor the long fade near the midpoint), with
 Earliest/Latest still available and a relaxed-threshold fallback ladder.
- **Never silently drops a file.** Unmatched or undetected files are copied
 through (configurable) instead of vanishing.
- **Robust filename parsing** - `S01E01E02`, `S01E15-16`, `S01E15-E16`, and
 `+ & and / _` title separators (CSV-guided so `Arnold & Lila` stays one title).
- **Modern GUI** (Windows 11-style theme, light/dark) that is fully thread-safe.
- **One shared engine** for the GUI and CLI; the CLI now honors config files.
- **Cross-platform** binary lookup (bundled `bin/` **or** system `PATH`).

## Requirements

- Python 3.10+
- `ffmpeg`, `ffprobe`, `mkvmerge` (see [below](#ffmpeg--mkvmerge-binaries))
- `tkinter` for the GUI (bundled with Python on Windows/macOS; on Linux install
 `python3-tk`)

## Setup

```bash
# 1) create and activate a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 2) install dependencies (optional modern theme)
pip install -r requirements.txt
```

Then launch the GUI: double-click **`run_gui.bat`** (Windows) or run
**`./run_gui.sh`** (macOS/Linux).

## FFmpeg / mkvmerge binaries

The three helper binaries are **not** committed to this repo. Provide them one of
two ways:

- **Bundled:** put `ffmpeg`, `ffprobe`, `mkvmerge` (`.exe` on Windows) in `./bin`.
 On Windows, `run_processor.bat` can download them for you automatically.
- **System PATH:** install them so they're on your `PATH` (e.g.
 `brew install ffmpeg mkvtoolnix` or `sudo apt-get install ffmpeg mkvtoolnix`).
 The app checks `bin/` first, then `PATH`.

## Usage (GUI)

1. **Process tab** - set the input folder (your double-episode files), output
 folder, and the episode-list CSV.
2. Optionally adjust the **Configuration tab** (or just leave *Auto-detect
 boundary* on).
3. Click **Start Processing** and watch the log.

Name your source files `Show Name - SxxExx - Title A + Title B.ext`.
Supported inputs: `.mkv .mp4 .avi .m4v .mov` (outputs are `.mkv`).

## Usage (CLI)

```bash
# use a saved show profile
python scene_splitter.py --cli --config configs/hey_arnold_config.json

# or pass options directly
python scene_splitter.py --cli --input "D:/in" --output "D:/out" --csv show.csv \
 --intro-duration 30

python scene_splitter.py --cli --help # full option list
```

## Episode lists

CSV format:

```csv
SeasonNumber,EpisodeNumber,EpisodeName,AbbvCombo
1,21,"Who, What, Where, Ed!",S01E21
1,22,Keeping Up with the Eds,S01E22
```

Ready-made lists for many shows live in `episode_lists/`. Build your own from
pasted text in the GUI's **Episode Manager** tab, or with
`python episode_formatter.py`. Titles containing commas are quoted automatically.

## Configuration reference

Saved as JSON in `configs/`. See `configs/sample_config.json` for an annotated
template. Key fields:

| Field | Meaning |
|-------|---------|
| `intro_duration` | Seconds of shared intro re-inserted into later episodes |
| `auto_target` | Derive the boundary from runtime (recommended) |
| `target_time` | Manual boundary time; used only when `auto_target` is false |
| `time_margin` | ± seconds to search around the expected boundary |
| `transition_selection` | `Smart` \| `Select Latest Transition` \| `Select Earliest Transition` |
| `split_point` | `At Start of Fade` \| `After Fade` |
| `detection_method` | `Comprehensive (All Methods)` \| `Standard Blackdetect Only` \| `Histogram Analysis` \| `Scene Change Detection` |
| `on_detection_failure` | `copy` \| `midpoint` \| `skip` |

## Troubleshooting

- **"mkvmerge/ffmpeg not found"** - put the binaries in `bin/` or on your `PATH`.
- **Split at the wrong point** - increase `time_margin`, or set `auto_target`
 off with a manual `target_time`; try `Select Earliest/Latest Transition`.
- **Episode not renamed** - make sure the title in the filename matches a title
 in your episode-list CSV (matching is fuzzy but not magic).
- **`tkinter not found`** - Windows: reinstall Python with "tcl/tk"; Ubuntu:
 `sudo apt-get install python3-tk`.
- Check the timestamped log in `logs/` for details.

## License

See [LICENSE](LICENSE).
