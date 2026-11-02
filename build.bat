@echo off
rem Builds dist\Capri\Capri.exe, and dist\Capri-Setup-<version>.exe if Inno Setup 6 is installed.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    py -3 -m venv .venv || python -m venv .venv || goto :error
)
.venv\Scripts\python.exe -m pip install -r requirements-build.txt || goto :error
rem Her neural voice (optional - the build works without it, with Windows voices only).
.venv\Scripts\python.exe -m pip install -r requirements-voice.txt && .venv\Scripts\python.exe -m pip install --no-deps --ignore-requires-python "kokoro-onnx>=0.5,<1" || echo Neural voice packages not installed - building without them.
rem Parakeet hearing's engine (optional - built in when it installs; the model downloads from Settings).
.venv\Scripts\python.exe -m pip install "sherpa-onnx>=1.12" || echo Parakeet engine not installed - building without it.
if not exist models\kokoro\kokoro-v1.0.int8.onnx .venv\Scripts\python.exe tools\download_voice.py
.venv\Scripts\python.exe tools\download_model.py || goto :error
.venv\Scripts\pyinstaller.exe --noconfirm --clean --distpath dist --workpath build packaging\capri.spec || goto :error
echo.
echo Built dist\Capri\Capri.exe

for /f %%v in ('.venv\Scripts\python.exe -c "import capri; print(capri.__version__)"') do set CAPRI_VERSION=%%v
set ISCC=
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set ISCC="%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if defined ISCC (
    %ISCC% /DAppVersion=%CAPRI_VERSION% packaging\capri.iss || goto :error
    echo Built dist\Capri-Setup-%CAPRI_VERSION%.exe
) else (
    echo Inno Setup 6 not found - skipped the installer. Get it free at https://jrsoftware.org/isdl.php
)
goto :eof
:error
echo Build failed.
pause
