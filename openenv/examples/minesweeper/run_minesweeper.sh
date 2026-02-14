#!/bin/bash
set -e

# Run WineMine (Minesweeper via Wine)
export INPUT_METHOD=xdotool
SRC_DIR=$(dirname "$0")
"$SRC_DIR/../../run.sh" "/usr/lib/x86_64-linux-gnu/wine/winemine.exe" "WineMine"
