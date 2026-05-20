# Local Audio Transcriber

A desktop application for transcribing audio files using OpenAI's Whisper API. Designed for meeting recordings and long audio files (1-2+ hours).

## Features

- **Modern GUI** - Clean interface with selectable theme (System, White, Dark)
- **Long File Support** - Automatically chunks files larger than 25MB for API compatibility
- **Smart Splitting** - Uses silence detection to split audio at natural pauses
- **Batch Processing** - Queue multiple files for transcription
- **Progress Tracking** - Real-time progress for each file and chunk
- **Live Recording Transcript** - Live transcript uses larger context windows and recent transcript context for better continuity

## Supported Audio Formats

- MP3, WAV, M4A, MP4, MKV, WebM, OGG, FLAC

Video containers (`.mp4`, `.mkv`, `.webm`) are accepted: their audio track is
extracted via FFmpeg before transcription. For `.mkv`, audio is always
re-encoded to MP3 internally because the OpenAI Whisper API does not accept
Matroska as an upload format.

## Prerequisites

### 1. Python 3.10+

Download from [python.org](https://www.python.org/downloads/)

### 2. FFmpeg (Required)

FFmpeg is needed for audio processing. Install it based on your operating system:

#### Windows

**Option A: Using winget (recommended)**
```powershell
winget install FFmpeg
```

**Option B: Using Chocolatey**
```powershell
choco install ffmpeg
```

**Option C: Manual Installation**
1. Download from [ffmpeg.org/download.html](https://ffmpeg.org/download.html)
2. Extract to a folder (e.g., `C:\ffmpeg`)
3. Add `C:\ffmpeg\bin` to your system PATH

#### macOS

```bash
brew install ffmpeg
```

#### Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install ffmpeg
```

### 3. OpenAI API Key Environment Variable

1. Sign up at [platform.openai.com](https://platform.openai.com/)
2. Create an API key at [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
3. Store it in your OS environment as `OPENAI_API_KEY`

## Installation

1. **Clone or download this repository**

2. **Create a virtual environment** (recommended)
   ```bash
   python -m venv .venv
   
   # Windows
   .venv\Scripts\activate
   
   # macOS/Linux
   source .venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install the app package (required for `python -m local_audio_transcriber`)**
   ```bash
   pip install -e .
   ```

## Usage

1. **Start the application**
   ```bash
   python -m local_audio_transcriber
   ```

   Alternative launchers:
   - Windows: `scripts/launch-local-audio-transcriber.bat`
   - Windows installer/bootstrap only: `scripts/install-local-audio-transcriber.bat`
   - macOS Terminal: `scripts/launch-local-audio-transcriber.sh`
   - macOS Finder: `scripts/launch-local-audio-transcriber.command`
   - macOS installer/bootstrap only: `scripts/install-local-audio-transcriber.sh`
   - The launchers call the installer script and then start the app

2. **Configure OpenAI**
   - The app reads the API key from an OS environment variable
   - Default environment variable name: `OPENAI_API_KEY`
   - You can change the environment variable name in Settings

3. **Add audio files**
   - Click "Add Audio Files" to browse and select files
   - Files appear in the queue with status indicators

4. **Start transcription**
   - Click "Start Transcription"
   - Watch progress for each file
   - Results are saved as `.txt` files in the output directory

5. **Open output directory quickly**
   - Use the `Output` button in the main header, or the `Open` button next to the output directory in Settings

## Configuration

Settings are stored in `~/.local-transcriber/config.json`:

- **Theme** - `System`, `White`, or `Dark`
- **OpenAI API Key Env Var Name** - OS environment variable name used to resolve the API key (default: `OPENAI_API_KEY`)
- **Output Directory** - Where transcription files are saved (default: `~/Documents/Transcriptions`)

Application logs are written to `~/.local-transcriber/logs/application.log` with
automatic rotation (up to 5 files of ~5MB each).

## Cost Estimation

OpenAI Whisper API pricing (as of 2024):
- **$0.006 per minute** of audio

| Recording Length | Estimated Cost |
|-----------------|----------------|
| 30 minutes      | ~$0.18         |
| 1 hour          | ~$0.36         |
| 2 hours         | ~$0.72         |

## Troubleshooting

### "FFmpeg not found" error
- Ensure FFmpeg is installed and in your system PATH
- Restart your terminal/application after installing FFmpeg
- On Windows, you may need to restart your computer

### "API Key Required" error
- Make sure `OPENAI_API_KEY` is set in your OS environment
- If you use a different environment variable name, configure that name in Settings
- Check that your API key has not expired or been revoked

### "ModuleNotFoundError: No module named 'tkinter'"
- Your Python installation does not include Tk (GUI toolkit)
- Install Python from [python.org](https://www.python.org/downloads/windows/) or use:
  - `winget install Python.Python.3.12`
- Recreate and reinstall in the project virtual environment:
  - `py -3.12 -m venv .venv`
  - `.venv\Scripts\python.exe -m pip install -r requirements.txt`
  - `.venv\Scripts\python.exe -m pip install -e .`

### Long processing time
- Large files are split into chunks and processed sequentially
- A 2-hour recording may take 5-15 minutes to process
- API response time depends on OpenAI server load

### Transcription quality issues
- Ensure good audio quality in the source file
- Background noise can reduce accuracy
- Consider using noise reduction tools before transcription

## Technical Details

### Chunking Strategy

Files over 25MB are automatically split:
- Target chunk duration: ~10 minutes
- Splits occur at detected silence points to preserve context
- Small overlap between chunks ensures no content is lost

### File Structure

```
local-transcriber/
├── pyproject.toml       # Modern Python project metadata
├── requirements.txt     # Dependency list for simple installs
├── scripts/
│   ├── install-local-audio-transcriber.bat
│   ├── install-local-audio-transcriber.sh
│   ├── launch-local-audio-transcriber.bat
│   ├── launch-local-audio-transcriber.sh
│   └── launch-local-audio-transcriber.command
├── src/
│   └── local_audio_transcriber/
│       ├── __init__.py
│       ├── __main__.py
│       ├── app.py
│       ├── transcriber.py
│       ├── streaming_transcriber.py
│       └── live_recorder.py
├── tests/
│   ├── test_config_manager.py
│   └── test_transcriber.py
└── README.md
```

## License

MIT License - Feel free to use and modify.
