@echo off
title Review Desk
rem Double-click this. It finds a Python that can open a window, because the
rem `python` on PATH here is a uv-managed 3.11 without the pieces we need.
setlocal
set "DESK=%~dp0review_desk.py"
set "PY=C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe"
if exist "%PY%" goto run
for /f "tokens=*" %%i in ('py -3.14 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%i"
if exist "%PY%" goto run
set "PY=python"
:run
"%PY%" "%DESK%" --seed %*
if errorlevel 1 (
  echo.
  echo The desk exited with an error. The line above says why.
  pause
)
