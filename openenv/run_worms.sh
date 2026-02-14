#!/bin/bash
# Run OpenEnv with Worms Armageddon
# Usage: ./run_worms.sh

set -e

# Change to script directory for Docker build context
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CONTAINER_NAME="openenv-worms"
SCREEN_WIDTH="${SCREEN_WIDTH:-800}"
SCREEN_HEIGHT="${SCREEN_HEIGHT:-600}"

# Detect architecture for Apple Silicon / ARM support
PLATFORM_FLAG=""
ARCH="$(uname -m)"
if [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then
    echo "Detected ARM architecture ($ARCH). Using --platform linux/amd64 for Wine compatibility."
    PLATFORM_FLAG="--platform linux/amd64"
fi

echo "🎮 OpenEnv - Worms Armageddon"
echo "============================="
echo "Screen: ${SCREEN_WIDTH}x${SCREEN_HEIGHT}"
echo ""

# Stop existing container
docker stop $CONTAINER_NAME 2>/dev/null || true
docker rm $CONTAINER_NAME 2>/dev/null || true

# Build image (ensure image is up to date)
echo "Building image..."
docker build $PLATFORM_FLAG -t openenv .

# Get the absolute path to the winvm/apps folder
PROJECT_ROOT="$(cd .. && pwd)"
APPS_PATH="$PROJECT_ROOT/winvm/apps"

if [ ! -d "$APPS_PATH/Worms" ]; then
    echo "Error: Worms directory not found at $APPS_PATH/Worms"
    echo "Please ensure you have downloaded Worms Armageddon to winvm/apps/Worms"
    exit 1
fi

# Run container
echo "Starting container with Worms Armageddon..."
docker run $PLATFORM_FLAG -d --name $CONTAINER_NAME \
  -p 8000:8000 \
  -p 9090:9090 \
  -e SCREEN_WIDTH=$SCREEN_WIDTH \
  -e SCREEN_HEIGHT=$SCREEN_HEIGHT \
  -e APP_FILE="/apps/Worms/WA.exe" \
  -e APP_ARGS="" \
  -e WINDOW_TITLE="Worms Armageddon" \
  -e INPUT_METHOD="xdotool" \
  -v "$APPS_PATH:/apps:ro" \
  openenv

# Wait for startup
echo "Waiting for services to start..."
sleep 10

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
echo "Logs:"
echo "  docker exec $CONTAINER_NAME cat /app/logs/wineapp.log"
echo "  docker exec $CONTAINER_NAME cat /app/logs/http_server.log"
