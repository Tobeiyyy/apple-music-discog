#!/bin/sh
# Double-click (macOS): starts the website and opens it in your browser. Close this window to stop it.
cd "$(dirname "$0")" || exit 1
command -v python3 >/dev/null || { echo "Python 3 is not installed. Get it from https://www.python.org/downloads/"; read -r _; exit 1; }
python3 server.py --open
