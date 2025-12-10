#!/bin/bash
# Run OpenEnv with Bomberman
# Usage: ./run_bomberman.sh

set -e

CONTAINER_NAME="openenv-bomberman"
SCREEN_WIDTH="${SCREEN_WIDTH:-800}"
SCREEN_HEIGHT="${SCREEN_HEIGHT:-600}"

echo "🎮 OpenEnv - Bomberman"
echo "======================"
echo "Screen: ${SCREEN_WIDTH}x${SCREEN_HEIGHT}"
echo ""

# Stop existing container
docker stop $CONTAINER_NAME 2>/dev/null || true
docker rm $CONTAINER_NAME 2>/dev/null || true

# Build image
echo "Building image..."
docker build -t openenv .

# Get the absolute path to the games folder
GAMES_PATH="$(cd "$(dirname "$0")" && pwd)/games"

# Run container with Bomberman
echo "Starting container with Bomberman..."
docker run -d --name $CONTAINER_NAME \
  -p 8000:8000 \
  -p 9090:9090 \
  -e SCREEN_WIDTH=$SCREEN_WIDTH \
  -e SCREEN_HEIGHT=$SCREEN_HEIGHT \
  -e APP_FILE="/games/Bomberman/med/mednafen.exe" \
  -e APP_ARGS="-video.fs 0 /games/Bomberman/med/game.pce" \
  -e WINDOW_TITLE="Mednafen" \
  -v "$GAMES_PATH:/games" \
  openenv

# Wait for startup
echo "Waiting for services to start..."
sleep 15

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
echo "Test mouse click:"
echo "  curl -X POST http://localhost:8000/step -H 'Content-Type: application/json' -d '{\"action_type\": \"mouse\", \"button\": \"left\", \"mouse_state\": \"down\", \"x\": 0.5, \"y\": 0.5}'"
echo ""
echo "Logs:"
echo "  docker exec $CONTAINER_NAME cat /app/logs/wineapp.log"
echo "  docker exec $CONTAINER_NAME cat /app/logs/syncinput.log"

