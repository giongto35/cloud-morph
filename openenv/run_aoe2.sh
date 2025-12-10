#!/bin/bash
# Run OpenEnv with Age of Empires 2
# Usage: ./run_aoe2.sh

set -e

CONTAINER_NAME="openenv-aoe2"
SCREEN_WIDTH="${SCREEN_WIDTH:-1024}"
SCREEN_HEIGHT="${SCREEN_HEIGHT:-768}"

echo "🎮 OpenEnv - Age of Empires 2"
echo "=============================="
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

# Run container with AoE2
echo "Starting container with AoE2..."
docker run -d --name $CONTAINER_NAME \
  -p 8000:8000 \
  -p 9090:9090 \
  -e SCREEN_WIDTH=$SCREEN_WIDTH \
  -e SCREEN_HEIGHT=$SCREEN_HEIGHT \
  -e APP_FILE="/games/Age of Empires 2/empires2.exe" \
  -e WINDOW_TITLE="Age of Empires" \
  -v "$GAMES_PATH:/games:ro" \
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












