@echo off
cd /d "%~dp0"
py -3.12 start_windows.py
if errorlevel 1 pause
