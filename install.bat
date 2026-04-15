@echo off
REM Polyglot installer for Windows.
REM Creates a local virtualenv, installs dependencies, and drops a
REM polyglot.bat launcher.

setlocal enableextensions
cd /d "%~dp0"

echo ==^> Polyglot installer
echo     Target directory: %CD%

where python >nul 2>&1
if errorlevel 1 (
  echo error: Python is required but was not found on PATH
  echo Install Python 3.9+ from https://www.python.org/downloads/
  exit /b 1
)

echo ==^> Creating virtualenv at .venv
python -m venv .venv
if errorlevel 1 (
  echo error: could not create virtualenv
  exit /b 1
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo error: dependency installation failed
  exit /b 1
)

> polyglot.bat echo @echo off
>> polyglot.bat echo setlocal
>> polyglot.bat echo cd /d "%%~dp0"
>> polyglot.bat echo ".venv\Scripts\python.exe" polyglot.py %%*

echo.
echo ==^> Done.
echo     1. set OPENAI_API_KEY=sk-...
echo     2. polyglot.bat
echo.
echo     Then press Ctrl+Alt+Space in any app and start speaking.
