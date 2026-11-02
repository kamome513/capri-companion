@echo off
rem Creates a local virtual environment on first run, then starts Capri.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Creating virtual environment...
    py -3 -m venv .venv || python -m venv .venv || goto :no_python
    .venv\Scripts\python.exe -m pip install --upgrade pip
)
rem Install / update packages when requirements.txt changes.
fc /b requirements.txt .venv\requirements.installed >nul 2>&1 || (
    .venv\Scripts\python.exe -m pip install -r requirements.txt || goto :pip_error
    copy /y requirements.txt .venv\requirements.installed >nul
)
rem Her neural voice. Optional: if it can't install, she just uses the Windows voices.
rem kokoro-onnx is pure Python but still labelled "Python < 3.14", hence --ignore-requires-python.
fc /b requirements-voice.txt .venv\voice.installed >nul 2>&1 || (
    .venv\Scripts\python.exe -m pip install -r requirements-voice.txt && .venv\Scripts\python.exe -m pip install --no-deps --ignore-requires-python "kokoro-onnx>=0.5,<1" && copy /y requirements-voice.txt .venv\voice.installed >nul || echo [capri] Couldn't install her neural voice - she'll use the Windows voices for now.
)
rem Parakeet hearing's engine (sherpa-onnx, ~20 MB). Optional: without it she hears with Vosk / Whisper.
if not exist .venv\hearing.installed (
    .venv\Scripts\python.exe -m pip install "sherpa-onnx>=1.12" && echo ok> .venv\hearing.installed || echo [capri] Couldn't install Parakeet's engine - Vosk will hear you.
)
rem Chatterbox (her old cloned voice) is gone: free the GBs it took, once.
if exist .venv\Lib\site-packages\chatterbox .venv\Scripts\python.exe tools\remove_chatterbox.py
rem One-time download of the offline speech model.
.venv\Scripts\python.exe tools\download_model.py
rem One-time download of her neural voice (~120 MB). Skips itself once installed.
if not exist models\kokoro\kokoro-v1.0.int8.onnx .venv\Scripts\python.exe tools\download_voice.py
.venv\Scripts\python.exe -m capri %*
goto :eof
:no_python
echo Couldn't create the Python environment. Install Python 3.10 or newer from python.org
echo (tick "Add python.exe to PATH" in the installer), then run this again.
pause
goto :eof
:pip_error
echo Installing Capri's Python packages failed - the lines above say which one and why.
echo Check your internet connection and run this again. If it keeps failing, send me those lines.
pause
