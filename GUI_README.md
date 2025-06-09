# Scene Segment Splitter - GUI Quick Start Guide

## Quick Start

### Windows Users:
1. Double-click `run_gui.bat`
2. The GUI will launch automatically

### Mac/Linux Users:
1. Make the script executable: `chmod +x run_gui.sh`
2. Run: `./run_gui.sh`

## Folder Structure

After first run, the following folders will be created:

```
Scene-Segment-Splitter/
├── input_videos/       # Place your video files here
├── output_videos/      # Processed videos will be saved here
├── configs/            # JSON configuration files
│   └── sample_config.json
├── logs/               # Processing logs
├── run_gui.bat         # Windows GUI launcher
├── run_gui.sh          # Linux/Mac GUI launcher
└── scene_splitter.py   # Main application
```

## GUI Overview

### Main Tab
- **Input Folder**: Select folder containing your video files
- **Output Folder**: Where split episodes will be saved
- **Episode CSV**: Database of episode names (default: episode_list.csv)
- **Start Processing**: Begin splitting videos
- **Processing Log**: Real-time status and progress

### Configuration Tab
- **Intro Duration**: Length of intro to extract (seconds)
- **Target Transition Time**: Where to look for episode break
- **Detection Parameters**: Fine-tune black frame detection
- **Save/Load Configuration**: Save settings for different shows

### Episode Manager Tab
- **Paste Episode Lists**: Copy from Wikipedia, IMDb, or any website
- **Auto-Format**: Automatically detects format and converts to CSV
- **Preview**: See the CSV before saving
- **Direct Load**: Load generated CSV directly into main tab

## Configuration Files

Configuration files are saved in the `configs/` folder. Create different profiles for different shows:

- `hey_arnold_config.json` - Settings for Hey Arnold!
- `rugrats_config.json` - Settings for Rugrats
- `custom_show_config.json` - Your custom settings

### Example Configuration:
```json
{
    "input_folder": "D:/Videos/Hey Arnold",
    "output_folder": "D:/Videos/Hey Arnold Split",
    "episode_csv": "hey_arnold_episodes.csv",
    "intro_duration": 47,
    "target_time": 710,
    "time_margin": 60
}
```

## Tips for Different Shows

Different shows may need different settings:

| Show | Intro Duration | Target Time | Notes |
|------|---------------|-------------|-------|
| Hey Arnold! | 47 seconds | 11:50 (710s) | Standard Nickelodeon format |
| Rugrats | 30 seconds | 11:00 (660s) | Shorter intro |
| Doug | 25 seconds | 11:30 (690s) | Varies by season |

## Command Line Mode

You can still use command line mode:
```bash
python scene_splitter.py --cli --input "input_videos" --output "output_videos"
```

## Troubleshooting

### "tkinter not found" Error:
- **Windows**: Reinstall Python with "tcl/tk and IDLE" option checked
- **Ubuntu/Debian**: `sudo apt-get install python3-tk`
- **macOS**: tkinter should be included with Python

### Videos not splitting correctly:
1. Check the Configuration tab settings
2. Try adjusting "Target Transition Time"
3. Increase "Time Margin" for more flexibility
4. Check the log for detected black frames

### Can't find episode names:
1. Ensure episode CSV is properly formatted
2. Check that episode names in filename match CSV
3. The fuzzy matching has 75% confidence threshold

## Adding New Shows

### Method 1: Episode Manager Tab (Recommended)
1. Open the **Episode Manager** tab
2. Copy episode list from any source:
   - Wikipedia episode list
   - IMDb episode guide
   - TheTVDB
   - Any website with episode listings
3. Paste into the text area
4. Click "Convert to CSV"
5. Review the preview and save

### Supported Episode Formats:
- `S01E01 - Episode Title` or `1x01 - Episode Title`
- `Season 1, Episode 1: Title`
- `1. Episode Title` (specify season number)
- `"Episode Title" (S1E1)`
- `Episode 1: Title`
- Wikipedia/IMDb formats

### Method 2: Manual CSV Creation
Create a CSV file with this format:
```csv
SeasonNumber,EpisodeNumber,EpisodeName,AbbvCombo
1,1,First Episode,S01E01
1,2,Second Episode,S01E02
```

### Method 3: Standalone Formatter
Use `episode_formatter.py` for batch conversions:
```bash
python episode_formatter.py
```

## Need Help?

- Check the processing log for detailed information
- Logs are saved with timestamps in the `logs/` folder
- Original command-line version still available via `run_processor.bat`