
# Video Processing Tool

  

## Features

- Automatically split video files containing two episodes

- Extract the intro segment and add it to the second episode

- Detect transitions between episodes using black frame detection

- Assign appropriate episode names and numbers based on the input filename

- Generate a log file with detailed processing information

  

## Prerequisites

1. Python 3.6 or later

2. FFmpeg installed and added to the system's `PATH` environment variable

  

## Setup

1.  **Create a Virtual Environment (venv)**:

- On Windows:

```

python -m venv myenv

myenv\Scripts\activate

```

- On macOS/Linux:

```

python3 -m venv myenv

source myenv/bin/activate

```

2.  **Install the Required Dependencies**:

```pip install -r requirements.txt```

  

This will install all the necessary Python packages listed in the `requirements.txt` file.

### Setup FFmpeg on Windows

1. **Download FFmpeg**:
   - Go to the official FFmpeg website (https://ffmpeg.org/download.html) and download the Windows build of FFmpeg.
   - Choose the "ffmpeg-git-full.7z" option from "Windows builds from gyan.dev" and download the file.

2. **Extract FFmpeg**:
   - Extract the downloaded ZIP file to a directory of your choice. For this example, we'll use `C:\ffmpeg`.
   - The extracted folder should contain the `bin`, `doc`, `lib`, and `share` directories.

3. **Add FFmpeg to the System PATH**:
   - Open the Start menu and search for "Environment Variables".
   - Click on "Edit the system environment variables".
   - In the Advanced System Properties window, click the "Environment Variables" button.
   - In the Environment Variables window, under the "System Variables" section, find the "Path" variable and click "Edit".
   - Click the "New" button and add the full path to the `bin` folder of your extracted FFmpeg directory (e.g., `C:\ffmpeg\bin`).
   - Click "OK" to save the changes and close all the windows.

4. **Verify the FFmpeg Installation**:
   - Open a new Command Prompt window.
   - Type `ffmpeg -version` and press Enter.
   - If the installation was successful, you should see the FFmpeg version information displayed.

Now that FFmpeg is installed and added to the system's PATH, you can proceed with the rest of the setup instructions in the README.md file.

### Setup FFmpeg on macOS

1.  **Install FFmpeg using Homebrew**:

- Open the Terminal application.

- Install Homebrew if you haven't already:

```

/usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"

```

- Install FFmpeg using Homebrew:

```

brew install ffmpeg

```

2.  **Verify the FFmpeg Installation**:

- Open a new Terminal window.

- Type `ffmpeg -version` and press Enter.

- If the installation was successful, you should see the FFmpeg version information displayed.

  

### Setup FFmpeg on Linux

1.  **Install FFmpeg using a Package Manager**:

- Open the Terminal application.

- Install FFmpeg using your Linux distribution's package manager. The command may vary depending on your distribution:

- For Ubuntu/Debian-based systems:

```

sudo apt-get update

sudo apt-get install ffmpeg

```

- For Fedora/CentOS/RHEL:

```

sudo dnf install ffmpeg

```

- For Arch Linux:

```

sudo pacman -S ffmpeg

```

2.  **Verify the FFmpeg Installation**:

- Open a new Terminal window.

- Type `ffmpeg -version` and press Enter.

- If the installation was successful, you should see the FFmpeg version information displayed.

  

## Usage

1.  **Prepare the Input Videos**: Place the video files you want to process in the `input_videos` directory.

2.  **Run the Script**:
- **On Windows**
	- Run run_processor.bat to start the script
	
- **On Mac/Linux**
	- Make the Shell Script Executable:
		- ```chmod +x process_videos.sh```
	- Run the Shell Script:
		- ```./process_videos.sh```

 - **Alternatively you can run the script manually:**
   - ```python video_processing.py```

3.  **Check the Log File**: The script will generate a log file named `video_processing_<timestamp>.log` in the current directory, containing details about the processing. This can be helpful if you are having issues with the splitting/saving.

**Purpose**: The `process_videos.sh` script simplifies the setup and execution process on Mac/Linux by automatically creating necessary directories and running the Python script. This ensures a seamless experience similar to the `.bat` file for Windows users.

  

## Customization

-  **Adjust the Intro Duration**: Modify the `INTRO_DURATION` constant in the `VideoProcessor` class to change the duration of the intro segment.

-  **Modify the Transition Detection**: Adjust the parameters (e.g., `d`, `pix_th`, `pic_th`) in the `detect_black_frames()` method to fine-tune the transition detection.

-  **Enhance the Episode Naming**: Modify the `_get_episode_names()` and `_find_matching_episode()` methods to improve the episode naming logic.

## License

This project is licensed under the [MIT License](LICENSE).

  

## Contributions

Contributions are welcome! If you find any issues or have suggestions for improvements, please feel free to submit a pull request.