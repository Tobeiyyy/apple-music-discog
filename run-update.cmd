@echo off
rem Weekly job: add new releases to all discography playlists.
cd /d "%~dp0"
python update.py >> update-run.log 2>&1
