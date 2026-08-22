@echo off
REM Benchmark de transcricao do ATIVAVID -- uma operacao so.
REM Uso:  tools\bench_transcricao\benchmark.cmd [corpus.json]
setlocal
cd /d "%~dp0..\.."
set CORPUS=%~1
if "%CORPUS%"=="" set CORPUS=corpus.json
uv run python tools\bench_transcricao\benchmark.py --corpus "%CORPUS%" --saida bench
endlocal
