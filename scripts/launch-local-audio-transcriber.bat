@echo off
cd /d "%~dp0\.."

call "%~dp0install-local-audio-transcriber.bat"
if errorlevel 1 (
  exit /b 1
)

set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
start "" /d "%CD%" ".venv\Scripts\pythonw.exe" -m local_audio_transcriber

exit /b 0
