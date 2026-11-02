@echo off
rem Downloads Capri's offline models (one time) into models\:
rem   speech recognition (~40 MB) and her neural voice (~120 MB).
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Run run.bat once first to set up Python packages.
    pause
    goto :eof
)
.venv\Scripts\python.exe tools\download_model.py
.venv\Scripts\python.exe tools\download_voice.py
pause
