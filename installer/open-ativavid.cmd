@echo off
setlocal
set "ROOT=%~dp0.."
if exist "%ROOT%\.venv\Scripts\pythonw.exe" (
  start "" /D "%ROOT%" "%ROOT%\.venv\Scripts\pythonw.exe" -X utf8 "%ROOT%\app\launcher.py"
  exit /b 0
)
if exist "%ROOT%\ATIVAVID.vbs" (
  start "" /D "%ROOT%" "%SystemRoot%\System32\wscript.exe" //nologo "%ROOT%\ATIVAVID.vbs"
  exit /b 0
)
exit /b 1
