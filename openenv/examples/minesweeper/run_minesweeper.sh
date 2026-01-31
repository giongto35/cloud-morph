#!/bin/bash
set -e

# Run Gnome Mines (Native Linux)
# Requires INPUT_METHOD=pyautogui
export INPUT_METHOD=pyautogui
SRC_DIR=$(dirname "$0")
"$SRC_DIR/../../run.sh" "/usr/lib/x86_64-linux-gnu/wine/winemine.exe" "WineMine"
