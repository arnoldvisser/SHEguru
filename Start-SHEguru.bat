@echo off
cd /d "%~dp0"
py -3 --version >nul 2>&1
if %errorlevel% equ 0 (
  py -3 server.py
) else (
  python --version >nul 2>&1
  if errorlevel 1 (
    echo SHEguru needs Python 3.10 or newer.
    echo Install it from https://www.python.org/downloads/windows/
    echo Then run Start-SHEguru.bat again.
  ) else (
    python server.py
  )
)
pause
