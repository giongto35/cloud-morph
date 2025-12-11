#!/bin/bash
# Run OpenEnv with Counter-Strike 1.6
# Usage: ./run_cs16.sh

set -e

CONTAINER_NAME="openenv-cs16"
SCREEN_WIDTH="${SCREEN_WIDTH:-800}"
SCREEN_HEIGHT="${SCREEN_HEIGHT:-600}"

echo "🎮 OpenEnv - Counter-Strike 1.6"
echo "==============================="
echo "Screen: ${SCREEN_WIDTH}x${SCREEN_HEIGHT}"
echo ""

# Stop existing container
docker stop $CONTAINER_NAME 2>/dev/null || true
docker rm $CONTAINER_NAME 2>/dev/null || true

# Build image
echo "Building image..."
docker build -t openenv .

# Resolve games path (allows override and external shared path)
DEFAULT_GAMES_PATH="$(cd "$(dirname "$0")" && pwd)/games"
ALT_GAMES_PATH="/home/giongto/code/cloud-morph/openenv/games"
GAMES_PATH="${GAMES_PATH_OVERRIDE:-$DEFAULT_GAMES_PATH}"

# Auto-switch to the external path if local games/ is missing
if [ ! -d "$GAMES_PATH" ] && [ -d "$ALT_GAMES_PATH" ]; then
  echo "Using external games path: $ALT_GAMES_PATH"
  GAMES_PATH="$ALT_GAMES_PATH"
fi

CS16_PATH="$GAMES_PATH/CS1.6"

# Basic asset check so we fail fast with a clear message
MISSING_ASSETS=0
if [ ! -d "$CS16_PATH" ]; then
  echo "⚠️  Missing Counter-Strike 1.6 files at $CS16_PATH"
  MISSING_ASSETS=1
fi
if [ ! -f "$CS16_PATH/hl.exe" ]; then
  echo "⚠️  Expected $CS16_PATH/hl.exe (from your own CS 1.6 install)"
  MISSING_ASSETS=1
fi
if [ ! -d "$CS16_PATH/cstrike" ]; then
  echo "⚠️  Expected $CS16_PATH/cstrike/ directory (game data)"
  MISSING_ASSETS=1
fi
if [ "$MISSING_ASSETS" -ne 0 ]; then
  echo ""
  echo "Place your legally obtained Counter-Strike 1.6 installation in:"
  echo "  $CS16_PATH"
  echo "Then rerun this script."
  exit 1
fi

# Choose executable (prefer hl.exe, fallback to cstrike.exe)
APP_FILE=""
for candidate in "$CS16_PATH/hl.exe" "$CS16_PATH/cstrike.exe"; do
  if [ -f "$candidate" ]; then
    APP_FILE="$candidate"
    break
  fi
done

if [ -z "$APP_FILE" ]; then
  echo "⚠️  Could not find hl.exe or cstrike.exe in $CS16_PATH"
  exit 1
fi

# Run container with CS 1.6
echo "Starting container with CS 1.6..."
docker run -d --name $CONTAINER_NAME \
  -p 8000:8000 \
  -p 9090:9090 \
  -e SCREEN_WIDTH=$SCREEN_WIDTH \
  -e SCREEN_HEIGHT=$SCREEN_HEIGHT \
  -e APP_FILE="${APP_FILE/\/home\/giongto\/code\/cloud-morph\/openenv\/games//games}" \
  -e APP_ARGS="-game cstrike -window -w ${SCREEN_WIDTH} -h ${SCREEN_HEIGHT}" \
  -e WINDOW_TITLE="Counter-Strike" \
  -v "$GAMES_PATH:/games" \
  openenv

# Wait for startup
echo "Waiting for services to start..."
sleep 20

# Check status
echo ""
echo "Service Status:"
docker exec $CONTAINER_NAME supervisorctl -s http://127.0.0.1:9001 status

echo ""
echo "✓ Ready!"
echo ""
echo "Viewer:   http://localhost:8000/viewer"
echo "Stream:   http://localhost:8000/stream"
echo ""
echo "Test keypress (W key):"
echo "  curl -X POST http://localhost:8000/step -H 'Content-Type: application/json' -d '{\"action_type\": \"key\", \"key\": 87, \"key_state\": \"down\"}'"
echo ""
echo "Logs:"
echo "  docker exec $CONTAINER_NAME cat /app/logs/wineapp.log"
echo "  docker exec $CONTAINER_NAME cat /app/logs/syncinput.log"




