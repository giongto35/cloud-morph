#!/bin/bash
# Run OpenEnv with StarCraft: Brood War
# Usage: ./run_starcraft.sh

set -e

# Change to script directory for Docker build context
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CONTAINER_NAME="openenv-starcraft"
SCREEN_WIDTH="${SCREEN_WIDTH:-640}"
SCREEN_HEIGHT="${SCREEN_HEIGHT:-480}"

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

echo "🎮 OpenEnv - StarCraft: Brood War"
echo "================================="
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

# Get the absolute path to the winvm/OpenEnvBinary folder
PROJECT_ROOT="$(cd .. && pwd)"
APPS_PATH="$PROJECT_ROOT/winvm/OpenEnvBinary"

if [ ! -d "$APPS_PATH/Starcraft" ]; then
    echo "Error: StarCraft directory not found at $APPS_PATH/Starcraft"
    echo "Run: git submodule update --init --recursive"
    exit 1
fi

# Run container with StarCraft
echo "Starting container with StarCraft..."
$CONTAINER_CMD run $PLATFORM_FLAG -d --name $CONTAINER_NAME \
  -p 8000:8000 \
  -p 9090:9090 \
  -e SCREEN_WIDTH=$SCREEN_WIDTH \
  -e SCREEN_HEIGHT=$SCREEN_HEIGHT \
  -e APP_FILE="/apps/Starcraft/StarCraft.exe" \
  -e APP_ARGS="" \
  -e WINDOW_TITLE="Brood War" \
  -e INPUT_METHOD="xdotool" \
  -v "$APPS_PATH:/apps:ro" \
  openenv

# Wait for startup
echo "Waiting for services to start..."
sleep 10

# Check status
echo ""
echo "Service Status:"
$CONTAINER_CMD exec $CONTAINER_NAME supervisorctl -s http://127.0.0.1:9001 status

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
echo "  $CONTAINER_CMD exec $CONTAINER_NAME cat /app/logs/wineapp.log"
echo "  $CONTAINER_CMD exec $CONTAINER_NAME cat /app/logs/syncinput.log"
