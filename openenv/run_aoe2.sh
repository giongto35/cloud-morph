#!/bin/bash
# Run OpenEnv with Age of Empires II (Classic 1.0c)
# Usage: ./run_aoe2.sh

set -e

# Change to script directory for Docker build context
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CONTAINER_NAME="openenv-aoe2"
SCREEN_WIDTH="${SCREEN_WIDTH:-800}"
SCREEN_HEIGHT="${SCREEN_HEIGHT:-600}"

# Use podman if docker is not available
if command -v docker &> /dev/null; then
    CONTAINER_CMD="docker"
elif command -v podman &> /dev/null; then
    CONTAINER_CMD="podman"
else
    echo "Error: Neither docker nor podman found"
    exit 1
fi

# Detect architecture for Apple Silicon / ARM support
PLATFORM_FLAG=""
ARCH="$(uname -m)"
if [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then
    echo "Detected ARM architecture ($ARCH). Using --platform linux/amd64 for Wine compatibility."
    PLATFORM_FLAG="--platform linux/amd64"
fi

echo "OpenEnv - Age of Empires II"
echo "==========================="
echo "Screen: ${SCREEN_WIDTH}x${SCREEN_HEIGHT}"
echo ""

# Stop existing container
$CONTAINER_CMD stop $CONTAINER_NAME 2>/dev/null || true
$CONTAINER_CMD rm $CONTAINER_NAME 2>/dev/null || true

# Build image
echo "Building image..."
if [ "$CONTAINER_CMD" = "podman" ]; then
    $CONTAINER_CMD build --isolation chroot $PLATFORM_FLAG -t openenv .
else
    $CONTAINER_CMD build $PLATFORM_FLAG -t openenv .
fi

# Get the absolute path to the winvm/apps folder
PROJECT_ROOT="$(cd .. && pwd)"
APPS_PATH="$PROJECT_ROOT/winvm/apps"

if [ ! -d "$APPS_PATH/AOE2" ]; then
    echo "Error: AOE2 directory not found at $APPS_PATH/AOE2"
    echo "Place game files at: $APPS_PATH/AOE2/Age of Empires 2/empires2.exe"
    exit 1
fi

# Run container with Age of Empires II
echo "Starting container with Age of Empires II..."
$CONTAINER_CMD run $PLATFORM_FLAG -d --name $CONTAINER_NAME \
  -p 8000:8000 \
  -p 9090:9090 \
  -e SCREEN_WIDTH=$SCREEN_WIDTH \
  -e SCREEN_HEIGHT=$SCREEN_HEIGHT \
  -e APP_FILE="/apps/AOE2/Age of Empires 2/empires2.exe" \
  -e APP_ARGS="" \
  -e WINDOW_TITLE="Age of Empires II" \
  -e INPUT_METHOD="xdotool" \
  -v "$APPS_PATH:/apps:ro" \
  openenv

# Wait for startup
echo "Waiting for services to start..."
sleep 15

# Check status
echo ""
echo "Service Status:"
$CONTAINER_CMD exec $CONTAINER_NAME supervisorctl -s http://127.0.0.1:9001 status

echo ""
echo "Ready!"
echo ""
echo "Viewer:   http://localhost:8000/viewer"
echo "Stream:   http://localhost:8000/stream"
echo ""
echo "Navigate to single player:"
echo "  python examples/aoe2/start_game.py"
echo ""
echo "Read game state from memory:"
echo "  python examples/aoe2/read_game_state.py --watch"
echo ""
echo "Logs:"
echo "  $CONTAINER_CMD exec $CONTAINER_NAME cat /app/logs/wineapp.log"
echo "  $CONTAINER_CMD exec $CONTAINER_NAME cat /app/logs/http_server.log"
