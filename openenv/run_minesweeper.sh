#!/bin/bash
# Run OpenEnv with classic Minesweeper (WINMINE.EXE)
# Usage: ./run_minesweeper.sh

set -e

CONTAINER_NAME="openenv-minesweeper"
SCREEN_WIDTH="${SCREEN_WIDTH:-800}"
SCREEN_HEIGHT="${SCREEN_HEIGHT:-600}"

echo "🎮 OpenEnv - Minesweeper"
echo "======================="
echo "Screen: ${SCREEN_WIDTH}x${SCREEN_HEIGHT}"
echo ""

# Stop existing container if present
docker stop $CONTAINER_NAME 2>/dev/null || true
docker rm $CONTAINER_NAME 2>/dev/null || true

# Build base image
echo "Building image..."
docker build -t openenv .

# Resolve absolute games path and verify Minesweeper binary exists
GAMES_PATH="$(cd "$(dirname "$0")" && pwd)/games"
if [ ! -f "$GAMES_PATH/minesweeper/WINMINE.EXE" ]; then
  echo "Missing WINMINE.EXE at $GAMES_PATH/minesweeper/WINMINE.EXE"
  exit 1
fi

# Run container with Minesweeper mounted in /games
echo "Starting container with Minesweeper..."
docker run -d --name $CONTAINER_NAME \
  -p 8000:8000 \
  -p 9090:9090 \
  -e SCREEN_WIDTH=$SCREEN_WIDTH \
  -e SCREEN_HEIGHT=$SCREEN_HEIGHT \
  -e APP_FILE="/games/minesweeper/WINMINE.EXE" \
  -e WINDOW_TITLE="Minesweeper" \
  -v "$GAMES_PATH:/games" \
  openenv

# Wait for services to become healthy
echo "Waiting for services to start..."
sleep 12

echo ""
echo "Service Status:"
docker exec $CONTAINER_NAME supervisorctl -s http://127.0.0.1:9001 status

echo ""
echo "✓ Ready!"
echo "Viewer:   http://localhost:8000/viewer"
echo "Stream:   http://localhost:8000/stream"
echo ""
echo "Sample reset call:"
echo "  curl -X POST http://localhost:8000/reset"
echo ""
echo "Logs:"
echo "  docker exec $CONTAINER_NAME cat /app/logs/wineapp.log"
echo "  docker exec $CONTAINER_NAME cat /app/logs/syncinput.log"


