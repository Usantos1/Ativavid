@echo off
REM Fallback de diagnostico (mostra console). Uso normal: ATIVAVID.vbs / atalho.
cd /d "%~dp0"
if exist "%~dp0ATIVAVID.vbs" (
  wscript //nologo "%~dp0ATIVAVID.vbs"
  exit /b 0
)
if exist "%~dp0vendor\ffmpeg\ffmpeg.exe" set "PATH=%~dp0vendor\ffmpeg;%PATH%"
if exist "%USERPROFILE%\ATIVAVID\ffmpeg\ffmpeg.exe" set "PATH=%USERPROFILE%\ATIVAVID\ffmpeg;%PATH%"
if exist "%~dp0.venv\Scripts\pythonw.exe" (
  start "" "%~dp0.venv\Scripts\pythonw.exe" -X utf8 app\launcher.py
  exit /b 0
)
uv run pythonw app\launcher.py
