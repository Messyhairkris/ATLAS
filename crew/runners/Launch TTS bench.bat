@echo off
title TTS bench - the crew's modules, live
rem Double-click this. It finds a Python that can reach Windows speech, because
rem the `python` on PATH here is a uv-managed 3.11 with no comtypes.
setlocal
set "BENCH=%~dp0tts_bench.py"
set "PY=C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe"
if exist "%PY%" goto run
for /f "tokens=*" %%i in ('py -3.14 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%i"
if exist "%PY%" goto run
set "PY=python"
:run
echo Launching the bench with %PY%
"%PY%" "%BENCH%" %*
if errorlevel 1 (
  echo.
  echo The bench exited with an error. The line above says why.
  pause
)
