@echo off
cd /d "%~dp0"
python spotify_to_lastfm.py
if errorlevel 1 pause
