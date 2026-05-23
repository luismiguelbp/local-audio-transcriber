# Local Audio Transcriber

A desktop app for transcribing local audio/video files and live recordings with OpenAI transcription models. It is designed for meeting recordings, long audio files, and quick live notes.

## Features

- File upload transcription for audio and supported video containers
- Batch queue with per-file progress
- Long-file support with automatic chunking
- Live recording with two modes:
  - `Live Transcript`: shows transcript updates while recording
  - `Record and Transcribe`: records first, then transcribes after you stop
- Selectable theme: `System`, `White`, or `Dark`
- Configurable output directory

## Supported Formats

- MP3, WAV, M4A, MP4, MKV, WebM, OGG, FLAC

For video containers (`.mp4`, `.mkv`, `.webm`), the app extracts the audio track with FFmpeg before transcription.

## Quick Start

### macOS/Linux

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
export OPENAI_API_KEY="your-api-key"
python -m local_audio_transcriber
```

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
setx OPENAI_API_KEY "your-api-key"
python -m local_audio_transcriber
```

After using `setx`, restart your terminal before launching the app so the new environment variable is available.

## Requirements

### Python 3.10+

Download Python from [python.org](https://www.python.org/downloads/).

### FFmpeg

FFmpeg is required for audio processing and video audio extraction.

Windows:

```powershell
winget install FFmpeg
```

macOS:

```bash
brew install ffmpeg
```

Linux:

```bash
sudo apt update
sudo apt install ffmpeg
```

### OpenAI API Key

Create an API key at [platform.openai.com/api-keys](https://platform.openai.com/api-keys), then store it in an environment variable named `OPENAI_API_KEY`.

macOS/Linux:

```bash
export OPENAI_API_KEY="your-api-key"
```

Windows PowerShell:

```powershell
setx OPENAI_API_KEY "your-api-key"
```

You can change the environment variable name in the app Settings if needed.

## Installation

Clone or download this repository, then from the project folder:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

On Windows, activate the virtual environment with:

```powershell
.venv\Scripts\Activate.ps1
```

## Usage

Start the app:

```bash
python -m local_audio_transcriber
```

Alternative launchers are available in `scripts/`:

- Windows: `scripts/launch-local-audio-transcriber.bat`
- macOS/Linux terminal: `scripts/launch-local-audio-transcriber.sh`
- macOS Finder: `scripts/launch-local-audio-transcriber.command`

### File Upload

1. Open the `File Upload` tab.
2. Add files with `Add Audio Files` or drag files into the drop zone.
3. Click `Start Transcription`.
4. Use `Output` to open the output directory.

### Live Recording

1. Open the `Live Recording` tab.
2. Select a microphone.
3. Optionally select system audio if available.
4. Choose a model and recording mode.
5. Click `Start Recording`.
6. Click `Stop Recording` when finished.

Use `Live Transcript` for immediate notes while recording. Use `Record and Transcribe` when you prefer the final transcript to be generated after stopping.

System audio capture is platform-dependent. Microphone recording works cross-platform; system loopback capture is currently supported through the Windows loopback backend.

## Configuration

Settings are stored in `~/.local-transcriber/config.json`:

- **Theme** - `System`, `White`, or `Dark`
- **OpenAI API Key Env Var Name** - environment variable name used to read the API key
- **Output Directory** - where transcript files are saved
- **Live Recording Mode** - default live recording behavior

Logs are written to `~/.local-transcriber/logs/application.log` with automatic rotation.

## Notes About Cost

Transcription uses OpenAI APIs, so usage may create costs on your OpenAI account. Check current pricing on the OpenAI platform before processing large batches or long recordings.

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

- Your Python installation does not include Tk
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

## Developer Notes

### Chunking Strategy

Files over 25MB are automatically split:

- Target chunk duration: about 10 minutes
- Splits occur at detected silence points to preserve context
- Small overlap between chunks ensures no content is lost

## License

MIT License - feel free to use and modify.
