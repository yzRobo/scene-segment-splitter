# Scene Segment Splitter - GUI Quick Start

## Launch

- **Windows:** double-click `run_gui.bat`
- **macOS/Linux:** `chmod +x run_gui.sh && ./run_gui.sh`

Both launchers use the project virtual environment (`.venv`) if present, create
the working folders, and install the optional theme. On first launch the app
downloads the required `ffmpeg`/`ffprobe`/`mkvmerge` binaries automatically
(Windows); on macOS/Linux install them via your package manager.

## Folders created on first run

```
scene-segment-splitter/
├── input_videos/ # put your double-episode files here
├── output_videos/ # split episodes are written here
├── configs/ # saved JSON configuration profiles
├── episode_lists/ # per-show episode CSVs
├── logs/ # timestamped processing logs
└── bin/ # ffmpeg / ffprobe / mkvmerge (not committed)
```

## The three tabs

### Process
- **Input / Output folders** and the **Episode CSV**.
- **Start Processing** / **Stop**, a live progress bar, and a scrolling log.

### Configuration
- **Intro duration** - seconds of shared intro re-inserted into later episodes.
- **Auto-detect boundary** (recommended) - derives the split point from the
 runtime, so no per-show tuning is needed. Turn it off to force a **Target time**.
- **Search margin** - how far to look around the expected boundary.
- **Detection method** - *Comprehensive* (blackdetect + luminance/scene-change
 fallbacks), or a single method.
- **Transition logic** - *Smart* (long fade nearest the midpoint), or
 Earliest/Latest.
- **Split point** - keep the fade with episode 2, or drop it (*After Fade*).
- **If no boundary found** - `copy` the source through, split at the `midpoint`,
 or `skip`.
- **Advanced blackdetect thresholds** for fine tuning.
- **Save / Load Configuration** profiles (per show).

### Episode Manager
- Paste an episode list (Wikipedia / IMDb / TheTVDB / plain text) and
 **Convert to CSV**. Recognizes `S01E01 - Title`, `1x01 - Title`,
 `Season 1, Episode 1: Title`, `1. Title`, bare numbered rows, and more.
- **Import / Export** a CSV, or **Use in Process tab** to load it immediately.
- Commas in titles are quoted correctly.

## File naming

Name inputs `Show Name - SxxExx - Title A + Title B.ext`. Titles may also be
joined with `&`, `and`, `/`, or `_`. The tool looks up each title in the episode
list and names the outputs from the **list** (correcting the source numbering).

## Tips for different shows

Different shows have different intros and runtimes. Start from a profile in
`configs/` or set:

| Show | Intro (s) | Notes |
|------|-----------|-------|
| Hey Arnold! | 47 | Standard Nickelodeon two-parter |
| Ed, Edd n Eddy | 30 | Shorter intro |
| Rugrats | 30 | Shorter intro |

With **Auto-detect boundary** on, the target time is derived automatically - you
usually only need to set the intro duration and pick the right episode CSV.

## Command line

```bash
python scene_splitter.py --cli --config configs/hey_arnold_config.json
python scene_splitter.py --cli --help
```

## Troubleshooting

- **`tkinter not found`** - Windows: reinstall Python with the "tcl/tk" option;
 Ubuntu/Debian: `sudo apt-get install python3-tk`.
- **Wrong split point** - raise the search margin, or switch transition logic.
- **Episode not renamed** - the filename title must match a title in the CSV.
- See the newest file in `logs/` for a full trace.
