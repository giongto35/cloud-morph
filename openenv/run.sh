#!/bin/bash
# OpenEnv Wine Environment Runner
# Usage: ./run.sh [app_file] [window_title] [app_args]

set -e

APP_FILE="${1:-notepad}"
WINDOW_TITLE="${2:-Notepad}"
APP_ARGS="${3:-}"
SCREEN_WIDTH="${SCREEN_WIDTH:-800}"
SCREEN_HEIGHT="${SCREEN_HEIGHT:-600}"
CONTAINER_NAME="openenv"

# Detect architecture for Apple Silicon / ARM support
PLATFORM_FLAG=""
ARCH="$(uname -m)"
if [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then
    echo "Detected ARM architecture ($ARCH). Using --platform linux/amd64 for Wine compatibility."
    PLATFORM_FLAG="--platform linux/amd64"
fi

echo "🎮 OpenEnv - Wine Environment"
echo "==================="
echo "App: $APP_FILE"
echo "Window: $WINDOW_TITLE"
echo "Screen: ${SCREEN_WIDTH}x${SCREEN_HEIGHT}"
echo ""

# Stop existing container
docker stop $CONTAINER_NAME 2>/dev/null || true
docker rm $CONTAINER_NAME 2>/dev/null || true

# Build image
echo "Building image (legacy mode)..."
DOCKER_BUILDKIT=0 docker build $PLATFORM_FLAG -t openenv .

# Run container
echo "Starting container..."
docker run $PLATFORM_FLAG -d --name $CONTAINER_NAME \
  -p 8000:8000 \
  -p 9090:9090 \
  -e SCREEN_WIDTH=$SCREEN_WIDTH \
  -e SCREEN_HEIGHT=$SCREEN_HEIGHT \
  -e APP_FILE="$APP_FILE" \
  -e APP_ARGS="$APP_ARGS" \
  -e WINDOW_TITLE="$WINDOW_TITLE" \
  -e INPUT_METHOD="${INPUT_METHOD:-xdotool}" \
  openenv

# Wait for startup
echo "Waiting for services..."
sleep 8

# Check status
echo ""
echo "Service Status:"
docker exec $CONTAINER_NAME supervisorctl -s http://127.0.0.1:9001 status

echo ""
echo "✓ Ready!"
echo ""
echo "API:      http://localhost:8000"
echo "Viewer:   http://localhost:8000/viewer"
echo "Stream:   http://localhost:8000/stream"
echo ""
echo "Test with:"
echo "  curl http://localhost:8000/health"
echo "  curl -X POST http://localhost:8000/reset"
echo ""
echo "Logs:"
echo "  docker exec $CONTAINER_NAME cat /app/logs/wineapp.log"
echo "  docker exec $CONTAINER_NAME cat /app/logs/syncinput.log"

