@echo off
setlocal
cd /d "%~dp0\.."

set "PROJECT_ROOT=%CD%"
set "VENV_DIR=.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "SETUP_MARKER=%VENV_DIR%\.local_audio_transcriber_setup_complete"
set "BASE_PYTHON="

call :select_base_python
if not defined BASE_PYTHON (
  echo.
  echo Could not find a Python interpreter with tkinter support.
  echo Install Python from python.org, then run this installer again.
  echo Suggested: winget install Python.Python.3.12
  echo.
  pause
  exit /b 1
)

if not exist "%VENV_PYTHON%" (
  echo Virtual environment not found. Creating "%VENV_DIR%"...
  call :create_venv
  if errorlevel 1 exit /b 1
)

call :venv_has_tkinter
if errorlevel 1 (
  echo Existing venv python has no tkinter. Recreating venv with: %BASE_PYTHON%
  rmdir /s /q "%VENV_DIR%" >nul 2>&1
  call :create_venv
  if errorlevel 1 exit /b 1
)

if not exist "%SETUP_MARKER%" (
  echo Running first-time setup...
  "%VENV_PYTHON%" -m pip install --upgrade pip
  if errorlevel 1 goto :setup_failed
  "%VENV_PYTHON%" -m pip install -r requirements.txt
  if errorlevel 1 goto :setup_failed
  "%VENV_PYTHON%" -m pip install -e .
  if errorlevel 1 goto :setup_failed
  type nul > "%SETUP_MARKER%"
) else (
  "%VENV_PYTHON%" -c "import openai, customtkinter, pydub, dotenv" >nul 2>&1
  if errorlevel 1 (
    echo Missing dependencies detected. Reinstalling...
    "%VENV_PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 goto :setup_failed
    "%VENV_PYTHON%" -m pip install -e .
    if errorlevel 1 goto :setup_failed
    type nul > "%SETUP_MARKER%"
  )
)

echo Installation/setup completed successfully.
exit /b 0

:setup_failed
echo.
echo Failed to install dependencies automatically.
echo Run these commands manually in "%PROJECT_ROOT%":
echo   %VENV_PYTHON% -m pip install -r requirements.txt
echo   %VENV_PYTHON% -m pip install -e .
echo.
pause
exit /b 1

:select_base_python
where py >nul 2>&1
if not errorlevel 1 (
  if not defined BASE_PYTHON (
    py -3.12 -c "import tkinter" >nul 2>&1
    if not errorlevel 1 set "BASE_PYTHON=py -3.12"
  )
  if not defined BASE_PYTHON (
    py -3.11 -c "import tkinter" >nul 2>&1
    if not errorlevel 1 set "BASE_PYTHON=py -3.11"
  )
  if not defined BASE_PYTHON (
    py -3.10 -c "import tkinter" >nul 2>&1
    if not errorlevel 1 set "BASE_PYTHON=py -3.10"
  )
  if not defined BASE_PYTHON (
    py -3 -c "import tkinter" >nul 2>&1
    if not errorlevel 1 set "BASE_PYTHON=py -3"
  )
)
if not defined BASE_PYTHON (
  python -c "import tkinter" >nul 2>&1
  if not errorlevel 1 set "BASE_PYTHON=python"
)
goto :eof

:create_venv
call %BASE_PYTHON% -m venv "%VENV_DIR%"
if errorlevel 1 (
  echo.
  echo Failed to create virtual environment using %BASE_PYTHON%.
  echo.
  pause
  exit /b 1
)
if not exist "%VENV_PYTHON%" (
  echo.
  echo Venv creation completed but python executable was not found.
  echo.
  pause
  exit /b 1
)
call :venv_has_tkinter
if errorlevel 1 (
  echo.
  echo Created venv still does not include tkinter.
  echo Install Python with Tcl/Tk support from python.org.
  echo.
  pause
  exit /b 1
)
goto :eof

:venv_has_tkinter
"%VENV_PYTHON%" -c "import tkinter" >nul 2>&1
if errorlevel 1 exit /b 1
exit /b 0
