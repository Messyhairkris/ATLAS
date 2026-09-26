@echo off
rem Double-click: a small window in the top-left corner showing what the crew is
rem doing, which campaign it belongs to, and when it is likely done.
rem Right-click the window to close it; double-click to switch compact/detailed.
start "" "C:\Users\user\AppData\Local\Programs\Python\Python314\pythonw.exe" "%~dp0status_overlay.py"
