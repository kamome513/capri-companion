@echo off
rem Better hearing for accents: installs Whisper (faster-whisper) into Capri's environment.
rem Then Settings -> Wake word -> Hearing -> Whisper -> Apply. Its model (~150 MB) downloads the first time it listens.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Run run.bat once first, so Capri's environment exists.
    pause
    goto :eof
)
echo Installing Whisper (faster-whisper)...
.venv\Scripts\python.exe -m pip install "faster-whisper>=1.0" || goto :failed
echo.
echo Done. In Capri: right-click her - Settings - Wake word - Hearing - Whisper - Apply.
pause
goto :eof
:failed
echo.
echo Whisper couldn't be installed on this Python version (the lines above say why).
echo Capri keeps using her normal hearing (Vosk). Installing Python 3.12 or 3.13 and re-running run.bat fixes it.
pause
