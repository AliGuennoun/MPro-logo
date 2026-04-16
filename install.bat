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

REM Console-visible launcher (useful for troubleshooting: shows errors,
REM pauses on crash). Run this one if something looks broken.
> polyglot.bat echo @echo off
>> polyglot.bat echo setlocal
>> polyglot.bat echo cd /d "%%~dp0"
>> polyglot.bat echo ".venv\Scripts\python.exe" polyglot.py %%*
>> polyglot.bat echo if errorlevel 1 pause

REM Silent launcher — launches the GUI with no console window.
REM Double-click Polyglot.vbs (or a shortcut to it) for the nicest UX.
> Polyglot.vbs echo Set sh = CreateObject("WScript.Shell")
>> Polyglot.vbs echo Set fso = CreateObject("Scripting.FileSystemObject")
>> Polyglot.vbs echo dir = fso.GetParentFolderName(WScript.ScriptFullName)
>> Polyglot.vbs echo sh.CurrentDirectory = dir
>> Polyglot.vbs echo sh.Run """" ^& dir ^& "\.venv\Scripts\pythonw.exe"" polyglot.py", 0, False

echo.
echo ==^> Done.
echo     1. set OPENAI_API_KEY=sk-...
echo     2. Double-click Polyglot.vbs  (silent, no console)
echo        or run polyglot.bat        (shows logs/errors)
echo.
echo     Then press Ctrl+Alt+Space in any app and start speaking.
