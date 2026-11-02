@echo off
rem Capri's chat brain: Ollama (free, runs on this PC, nothing leaves it) + the llama3.2 model (~2 GB).
rem Uses winget (built into Windows 10/11). Ollama starts with Windows; Capri finds it by herself.
cd /d "%~dp0"
where ollama >nul 2>&1 || (
    echo Installing Ollama...
    winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements || goto :manual
)
set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Ollama"
echo Downloading her chat model (llama3.2, ~2 GB)...
ollama pull llama3.2 || goto :manual
echo.
echo Done. Say "Hey Capri" and just talk to her - or open her chat window.
pause
goto :eof
:manual
echo.
echo Couldn't set it up automatically. Install Ollama from https://ollama.com, then open a terminal and run:
echo     ollama pull llama3.2
pause
